from flask_mail import Message
from models import ParkingSpot, User, ParkingLot, ParkingRecord, db
from datetime import datetime, timedelta
from sqlalchemy import func
import calendar
import csv
import io
from celery_worker import celery

# Import Flask app and mail from main module
def get_flask_app():
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from main import create_app
    return create_app()

def get_mail_instance():
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from main import mail
    return mail

@celery.task(bind=True)
def free_expired_spots(self):
    
    flask_app = get_flask_app()
    with flask_app.app_context():
        try:
            now = datetime.utcnow()
            # Find spots that have been occupied for more than 24 hours without proper checkout
            expired_records = ParkingRecord.query.filter(
                ParkingRecord.left_at == None,
                ParkingRecord.parked_at < (now - timedelta(hours=24))
            ).all()

            freed_count = 0
            for record in expired_records:
                # Auto-checkout the expired booking
                record.left_at = now
                duration = now - record.parked_at
                hours = duration.total_seconds() / 3600
                lot = record.spot.lot
                record.parking_cost = round(hours * float(lot.price_per_hour), 2)
                
                # Free the spot
                record.spot.status = 'A'
                freed_count += 1

            db.session.commit()
            print(f"✅ {freed_count} expired spots freed automatically.")
            return {'freed_spots': freed_count}
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error freeing expired spots: {str(e)}")
            return {'error': str(e)}
        
@celery.task(bind=True)
def send_email_task(self, to, subject, body, html_body=None):
   
    flask_app = get_flask_app()
    mail = get_mail_instance()
    
    with flask_app.app_context():
        try:
            if '@' not in to:
                print(f"❌ Invalid recipient: {to}")
                return {'status': 'failed', 'message': 'Invalid email address'}
            
            msg = Message(
                subject=subject,
                recipients=[to],
                body=body,
                html=html_body,
                sender=flask_app.config['MAIL_DEFAULT_SENDER']
            )
            mail.send(msg)
            print(f"✅ Email sent to {to}")
            return {'status': 'success', 'recipient': to}
            
        except Exception as e:
            print(f"❌ Failed to send email to {to}: {str(e)}")
            return {'status': 'failed', 'message': str(e)}

@celery.task(bind=True)
def get_inactive_users_today(self):
    
    flask_app = get_flask_app()
    with flask_app.app_context():
        try:
            today = datetime.now().date()
            
            # Get users who have parking records today
            users_active_today = db.session.query(ParkingRecord.user_id).filter(
                func.date(ParkingRecord.parked_at) == today
            ).distinct().subquery()
            
            # Get users who don't have parking records today
            inactive_users = User.query.filter(
                ~User.id.in_(users_active_today)
            ).all()
            
            return [{'id': user.id, 'email': user.email, 'username': user.username, 'fullname': user.fullname} 
                   for user in inactive_users if user.email]
            
        except Exception as e:
            print(f"❌ Error fetching inactive users: {str(e)}")
            return []

@celery.task(bind=True)
def send_instant_new_lot_email(self, parking_lot_id):
    
    flask_app = get_flask_app()
    with flask_app.app_context():
        try:
            # Get parking lot details
            parking_lot = ParkingLot.query.get(parking_lot_id)
            if not parking_lot:
                print(f"❌ Parking lot {parking_lot_id} not found")
                return {'status': 'failed', 'message': 'Parking lot not found'}
            
            # Get all users with email addresses
            users = User.query.filter(User.email != None, User.email != '').all()
            
            if not users:
                print("No users to send emails to")
                return {'status': 'success', 'sent_count': 0}
            
            subject = f"🚗 New Parking Lot Available: {parking_lot.lot_name}"
            total_spots = parking_lot.number_of_spots
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>New Parking Lot Available</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                              color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .lot-details {{ background: white; border-radius: 8px; padding: 20px; margin: 20px 0; 
                                   border-left: 4px solid #667eea; }}
                    .cta-button {{ display: inline-block; background: #667eea; color: white; 
                                  padding: 12px 30px; text-decoration: none; border-radius: 5px; 
                                  margin: 20px 0; }}
                    .footer {{ text-align: center; color: #666; margin-top: 30px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🚗 New Parking Lot Available!</h1>
                        <p>A new parking location has been added to our system</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hello!</h2>
                        <p>Great news! Our admin has just added a new parking lot to the system. 
                           Book your spot now before it fills up!</p>
                        
                        <div class="lot-details">
                            <h3>📍 {parking_lot.lot_name}</h3>
                            <p><strong>Location:</strong> {parking_lot.address}</p>
                            <p><strong>Pincode:</strong> {parking_lot.pincode}</p>
                            <p><strong>Price:</strong> ₹{parking_lot.price_per_hour}/hour</p>
                            <p><strong>Available Spots:</strong> {total_spots} spots available</p>
                            <p><strong>Added:</strong> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                        </div>
                        
                        <div style="text-align: center;">
                            <a href="#" class="cta-button">🔍 Book Now</a>
                        </div>
                        
                        <p><strong>💡 Tip:</strong> Popular parking lots fill up quickly. Book your spot early!</p>
                    </div>
                    
                    <div class="footer">
                        <p>This is an automated notification from Parking Management System</p>
                        <p>📧 Sent on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Send emails to all users
            sent_count = 0
            failed_count = 0
            
            for user in users:
                try:
                    # Queue individual email tasks
                    send_email_task.delay(
                        to=user.email,
                        subject=subject,
                        body=f"New parking lot '{parking_lot.lot_name}' has been added at {parking_lot.address}",
                        html_body=html_content
                    )
                    sent_count += 1
                except Exception as e:
                    print(f"❌ Failed to queue email for {user.email}: {str(e)}")
                    failed_count += 1
            
            print(f"✅ Instant emails queued for {sent_count} users about new lot: {parking_lot.lot_name}")
            return {
                'status': 'success',
                'sent_count': sent_count,
                'failed_count': failed_count,
                'lot_name': parking_lot.lot_name
            }
            
        except Exception as e:
            print(f"❌ Error sending instant new lot emails: {str(e)}")
            return {'status': 'failed', 'message': str(e)}

@celery.task(bind=True)
def send_daily_inactive_reminder(self):
   
    flask_app = get_flask_app()
    with flask_app.app_context():
        try:
            # Get inactive users
            inactive_users_data = get_inactive_users_today()
            
            if not inactive_users_data:
                print("✅ No inactive users found - all users were active today!")
                return {'status': 'success', 'sent_count': 0, 'message': 'All users were active today'}
            
            # Get available parking lots
            available_lots = ParkingLot.query.filter_by(is_active=True).all()
            
            if not available_lots:
                print("❌ No available parking lots found")
                return {'status': 'failed', 'message': 'No available parking lots'}
            
            # Build lots HTML
            lots_html = ""
            try:
                for lot in available_lots:
                    total_spots = ParkingSpot.query.filter_by(lot_id=lot.id, is_active=True).count()
                    occupied_spots = ParkingSpot.query.filter_by(lot_id=lot.id, status='O', is_active=True).count()
                    available_spots = total_spots - occupied_spots
                    
                    lots_html += f"""
                    <div style="background: white; border-radius: 8px; padding: 15px; margin: 10px 0; border-left: 3px solid #28a745;">
                        <h4 style="margin: 0 0 10px 0; color: #333;">📍 {lot.lot_name}</h4>
                        <p style="margin: 5px 0; color: #666;">
                            <strong>Location:</strong> {lot.address} ({lot.pincode})<br>
                            <strong>Price:</strong> ₹{lot.price_per_hour}/hour<br>
                            <strong>Available:</strong> {available_spots}/{total_spots} spots
                        </p>
                    </div>
                    """
                    
            except Exception as e:
                print(f"❌ Error building lots HTML: {str(e)}")
                lots_html = "<p>Error loading parking lot details.</p>"
            
            subject = "🅿️ Don't Miss Out - Parking Spots Available!"
            sent_count = 0
            failed_count = 0
            
            # Send emails to inactive users
            for user_data in inactive_users_data:
                try:
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="UTF-8">
                        <title>Parking Reminder</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                            .header {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); 
                                      color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                            .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
                            .cta-button {{ display: inline-block; background: #28a745; color: white; 
                                          padding: 12px 30px; text-decoration: none; border-radius: 5px; 
                                          margin: 20px 0; }}
                            .footer {{ text-align: center; color: #666; margin-top: 30px; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="header">
                                <h1>🅿️ Don't Miss Out!</h1>
                                <p>Parking spots are available for booking</p>
                            </div>
                            
                            <div class="content">
                                <h2>Hello {user_data['fullname'] or user_data['username']}!</h2>
                                <p>We noticed you haven't visited our parking system today. 
                                   Don't miss out on available parking spots!</p>
                                
                                <h3>🚗 Available Parking Lots:</h3>
                                {lots_html}
                                
                                <div style="text-align: center;">
                                    <a href="#" class="cta-button">🔍 Browse & Book Now</a>
                                </div>
                                
                                <p><strong>⏰ Reminder:</strong> This email is sent daily at 6 PM to users who haven't 
                                   been active today. Stay ahead and book your parking spot!</p>
                            </div>
                            
                            <div class="footer">
                                <p>Daily Parking Reminder - Parking Management System</p>
                                <p>📧 Sent on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    
                    # Queue email task
                    send_email_task.delay(
                        to=user_data['email'],
                        subject=subject,
                        body=f"Hello {user_data['fullname'] or user_data['username']}, don't miss out on available parking spots!",
                        html_body=html_content
                    )
                    sent_count += 1
                    
                except Exception as e:
                    print(f"❌ Error queuing email for user {user_data['username']}: {str(e)}")
                    failed_count += 1
            
            print(f"✅ Daily reminder emails queued for {sent_count} inactive users")
            return {
                'status': 'success',
                'sent_count': sent_count,
                'failed_count': failed_count,
                'inactive_users': len(inactive_users_data)
            }
            
        except Exception as e:
            print(f"❌ Error sending daily reminder emails: {str(e)}")
            return {'status': 'failed', 'message': str(e)}

@celery.task(bind=True)
def generate_monthly_report(self, user_id):
   
    flask_app = get_flask_app()
    mail = get_mail_instance()
    
    with flask_app.app_context():
        try:
            # Get user
            user = User.query.get(user_id)
            if not user:
                print(f"❌ User {user_id} not found")
                return {'status': 'failed', 'message': 'User not found'}
            
            # Get last month's data
            today = datetime.now()
            if today.month == 1:
                last_month = 12
                last_year = today.year - 1
            else:
                last_month = today.month - 1
                last_year = today.year
            
            # Get first and last day of last month
            first_day = datetime(last_year, last_month, 1)
            last_day = datetime(last_year, last_month, calendar.monthrange(last_year, last_month)[1], 23, 59, 59)
            month_name = calendar.month_name[last_month]
            
            # Query user's parking records for last month
            records = db.session.query(ParkingRecord).join(
                ParkingSpot, ParkingRecord.spot_id == ParkingSpot.id
            ).join(
                ParkingLot, ParkingSpot.lot_id == ParkingLot.id
            ).filter(
                ParkingRecord.user_id == user_id,
                ParkingRecord.parked_at >= first_day,
                ParkingRecord.parked_at <= last_day
            ).all()
            
            if not records:
                print(f"📊 No parking records found for user {user.username} in {month_name} {last_year}")
                # Still send email saying no activity
                total_bookings = 0
                total_spent = 0
                most_used_lot = "No bookings"
                avg_duration = "0 hours"
                records_html = "<p style='text-align: center; color: #666;'>No parking activity in this month.</p>"
            else:
                # Calculate statistics
                total_bookings = len(records)
                total_spent = sum([r.parking_cost or 0 for r in records])
                
                # Find most used parking lot
                lot_usage = {}
                total_duration = timedelta()
                
                for record in records:
                    lot_name = record.spot.lot.lot_name
                    lot_usage[lot_name] = lot_usage.get(lot_name, 0) + 1
                    
                    # Calculate duration
                    if record.left_at:
                        duration = record.left_at - record.parked_at
                        total_duration += duration
                
                most_used_lot = max(lot_usage.items(), key=lambda x: x[1])[0] if lot_usage else "N/A"
                avg_duration_hours = total_duration.total_seconds() / 3600 / total_bookings if total_bookings > 0 else 0
                avg_duration = f"{avg_duration_hours:.1f} hours"
                
                # Generate records HTML table
                records_html = """
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="border: 1px solid #ddd; padding: 12px; text-align: left;">Date</th>
                            <th style="border: 1px solid #ddd; padding: 12px; text-align: left;">Location</th>
                            <th style="border: 1px solid #ddd; padding: 12px; text-align: left;">Vehicle</th>
                            <th style="border: 1px solid #ddd; padding: 12px; text-align: left;">Duration</th>
                            <th style="border: 1px solid #ddd; padding: 12px; text-align: left;">Cost</th>
                        </tr>
                    </thead>
                    <tbody>
                """
                
                for record in records[:15]:  # Show latest 15 records
                    duration_str = "Ongoing"
                    if record.left_at:
                        duration = record.left_at - record.parked_at
                        hours = duration.total_seconds() / 3600
                        duration_str = f"{hours:.1f}h"
                    
                    records_html += f"""
                    <tr>
                        <td style="border: 1px solid #ddd; padding: 8px;">{record.parked_at.strftime('%Y-%m-%d')}</td>
                        <td style="border: 1px solid #ddd; padding: 8px;">{record.spot.lot.lot_name}</td>
                        <td style="border: 1px solid #ddd; padding: 8px;">{record.vehicle_number}</td>
                        <td style="border: 1px solid #ddd; padding: 8px;">{duration_str}</td>
                        <td style="border: 1px solid #ddd; padding: 8px;">₹{record.parking_cost or 0:.2f}</td>
                    </tr>
                    """
                
                records_html += "</tbody></table>"
                
                if len(records) > 15:
                    records_html += f"<p style='color: #666; font-style: italic;'>... and {len(records) - 15} more bookings</p>"
            
            # Create HTML email content
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Monthly Parking Report - {month_name} {last_year}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
                    .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #4a90e2 0%, #7b68ee 100%); 
                              color: white; padding: 40px; text-align: center; border-radius: 15px 15px 0 0; }}
                    .content {{ background: #f8f9fa; padding: 40px; border-radius: 0 0 15px 15px; }}
                    .stats-grid {{ display: flex; flex-wrap: wrap; gap: 20px; margin: 30px 0; }}
                    .stat-card {{ background: white; border-radius: 12px; padding: 25px; flex: 1; min-width: 200px;
                                 border-left: 5px solid #4a90e2; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                    .stat-number {{ font-size: 32px; font-weight: bold; color: #4a90e2; margin: 0; }}
                    .stat-label {{ color: #666; margin: 5px 0 0 0; font-size: 14px; }}
                    .section {{ background: white; border-radius: 12px; padding: 30px; margin: 25px 0; 
                               box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                    .footer {{ text-align: center; color: #666; margin-top: 40px; padding: 20px; }}
                    h2 {{ color: #4a90e2; border-bottom: 2px solid #4a90e2; padding-bottom: 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>📊 Monthly Parking Report</h1>
                        <h2>{month_name} {last_year}</h2>
                        <p>Your comprehensive parking activity summary</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hello {user.fullname or user.username}!</h2>
                        <p>Here's your detailed parking activity report for <strong>{month_name} {last_year}</strong>. 
                           This automated report helps you track your parking patterns and expenses.</p>
                        
                        <div class="stats-grid">
                            <div class="stat-card">
                                <p class="stat-number">{total_bookings}</p>
                                <p class="stat-label">Total Bookings</p>
                            </div>
                            <div class="stat-card">
                                <p class="stat-number">₹{total_spent:.2f}</p>
                                <p class="stat-label">Total Spent</p>
                            </div>
                            <div class="stat-card">
                                <p class="stat-number" style="font-size: 20px;">{most_used_lot}</p>
                                <p class="stat-label">Most Used Location</p>
                            </div>
                            <div class="stat-card">
                                <p class="stat-number" style="font-size: 20px;">{avg_duration}</p>
                                <p class="stat-label">Avg. Duration</p>
                            </div>
                        </div>
                        
                        <div class="section">
                            <h2>📋 Booking Details</h2>
                            {records_html}
                        </div>
                        
                        <div class="section">
                            <h2>💡 Insights & Tips</h2>
                            <ul style="line-height: 1.8;">
                                <li><strong>Peak Usage:</strong> {most_used_lot} was your go-to parking location this month.</li>
                                <li><strong>Average Cost:</strong> You spent an average of ₹{(total_spent/total_bookings) if total_bookings > 0 else 0:.2f} per booking.</li>
                                <li><strong>Tip:</strong> Consider booking during off-peak hours for better availability!</li>
                            </ul>
                        </div>
                    </div>
                    
                    <div class="footer">
                        <p><strong>Monthly Parking Report</strong> - Parking Management System</p>
                        <p>📧 Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                        <p style="font-size: 12px; color: #999;">This report is automatically generated on the 1st of every month</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Send email
            subject = f"📊 Your Monthly Parking Report - {month_name} {last_year}"
            
            if user.email:
                # Use the send_email_task to send the email
                result = send_email_task.delay(
                    to=user.email,
                    subject=subject,
                    body=f"Your monthly parking report for {month_name} {last_year} is ready!",
                    html_body=html_content
                )
                print(f"✅ Monthly report queued for {user.email} for {month_name} {last_year}")
                
                return {
                    'status': 'success',
                    'message': f'Monthly report queued for {user.email}',
                    'stats': {
                        'total_bookings': total_bookings,
                        'total_spent': total_spent,
                        'most_used_lot': most_used_lot
                    }
                }
            else:
                print(f"❌ No email address for user {user.username}")
                return {'status': 'failed', 'message': 'No email address found'}
                
        except Exception as e:
            print(f"❌ Error generating monthly report for user {user_id}: {str(e)}")
            return {'status': 'failed', 'message': str(e)}

@celery.task(bind=True)
def send_all_monthly_reports(self):
    
    flask_app = get_flask_app()
    with flask_app.app_context():
        try:
            # Get all users with email addresses
            users = User.query.filter(User.email != None, User.email != '').all()
            
            if not users:
                print("❌ No users with email addresses found")
                return {'status': 'failed', 'message': 'No users found'}
            
            sent_count = 0
            failed_count = 0
            
            # Generate monthly report for each user
            for user in users:
                try:
                    # Queue individual monthly report tasks
                    generate_monthly_report.delay(user.id)
                    sent_count += 1
                except Exception as e:
                    print(f"❌ Failed to queue monthly report for user {user.username}: {str(e)}")
                    failed_count += 1
            
            print(f"✅ Monthly reports queued for {sent_count} users")
            return {
                'status': 'success',
                'sent_count': sent_count,
                'failed_count': failed_count,
                'total_users': len(users)
            }
            
        except Exception as e:
            print(f"❌ Error sending monthly reports to all users: {str(e)}")
            return {'status': 'failed', 'message': str(e)}

@celery.task(bind=True)
def export_user_parking_csv(self, user_id):
    
    flask_app = get_flask_app()
    mail = get_mail_instance()
    
    with flask_app.app_context():
        try:
            # Get user
            user = User.query.get(user_id)
            if not user:
                print(f"❌ User {user_id} not found")
                return {'status': 'failed', 'message': 'User not found'}
            
            print(f"📊 Starting CSV export for user: {user.username}")
            
            # Get all parking records for the user
            records = db.session.query(ParkingRecord).join(
                ParkingSpot, ParkingRecord.spot_id == ParkingSpot.id
            ).join(
                ParkingLot, ParkingSpot.lot_id == ParkingLot.id
            ).filter(
                ParkingRecord.user_id == user_id
            ).order_by(ParkingRecord.parked_at.desc()).all()
            
            print(f"📊 Found {len(records)} parking records")
            
            # Create CSV content
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer)
            
            # Write CSV headers (as per requirements)
            csv_writer.writerow([
                'Slot ID',
                'Spot ID', 
                'Parking Lot Name',
                'Address',
                'Vehicle Number',
                'Parked At',
                'Left At',
                'Duration (Hours)',
                'Cost (₹)',
                'Remarks'
            ])
            
            # Write data rows
            for record in records:
                # Calculate duration
                duration_hours = 0
                if record.left_at:
                    duration = record.left_at - record.parked_at
                    duration_hours = round(duration.total_seconds() / 3600, 2)
                
                # Create remarks
                status = "Completed" if record.left_at else "Active"
                remarks = f"Status: {status}"
                
                csv_writer.writerow([
                    record.id,  # Slot ID
                    record.spot.id,  # Spot ID
                    record.spot.lot.lot_name,  # Parking Lot Name
                    f"{record.spot.lot.address}, {record.spot.lot.pincode}",  # Address
                    getattr(record, 'vehicle_number', 'N/A'),  # Vehicle Number
                    record.parked_at.strftime('%Y-%m-%d %H:%M:%S'),  # Parked At
                    record.left_at.strftime('%Y-%m-%d %H:%M:%S') if record.left_at else 'Still Parked',  # Left At
                    duration_hours,  # Duration
                    record.parking_cost or 0,  # Cost
                    remarks  # Remarks
                ])
            
            csv_content = csv_buffer.getvalue()
            csv_buffer.close()
            
            # Send email with CSV attachment
            if user.email:
                subject = f"Parking History Export - {datetime.now().strftime('%Y-%m-%d')}"
                
                html_content = f"""
                <h2>🚗 Parking History Export</h2>
                <p>Hello {user.fullname or user.username},</p>
                <p>Your parking history CSV export is ready!</p>
                <p><strong>Total Records:</strong> {len(records)}</p>
                <p><strong>Export Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>The CSV file is attached to this email.</p>
                <br>
                <p>Best regards,<br>ParkEasy Team</p>
                """
                
                # Create email message
                msg = Message(
                    subject=subject,
                    recipients=[user.email],
                    html=html_content,
                    sender=flask_app.config['MAIL_DEFAULT_SENDER']
                )
                
                # Attach CSV file
                filename = f"parking_history_{user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                msg.attach(
                    filename=filename,
                    content_type='text/csv',
                    data=csv_content
                )
                
                # Send email
                mail.send(msg)
                print(f"✅ CSV export sent to {user.email} with {len(records)} records")
                
                return {
                    'status': 'success',
                    'message': f'CSV export sent to {user.email}',
                    'record_count': len(records)
                }
            else:
                print(f"❌ No email address for user {user.username}")
                return {'status': 'failed', 'message': 'No email address found'}
                
        except Exception as e:
            print(f"❌ Error exporting CSV for user {user_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'status': 'failed', 'message': str(e)}






# Additional utility tasks
@celery.task(bind=True)
def check_parking_lot_availability(self):
    
    flask_app = get_flask_app()
    with flask_app.app_context():
        try:
            lots = ParkingLot.query.filter_by(is_active=True).all()
            updated_lots = []
            
            for lot in lots:
                total_spots = ParkingSpot.query.filter_by(lot_id=lot.id, is_active=True).count()
                occupied_spots = ParkingSpot.query.filter_by(lot_id=lot.id, status='O', is_active=True).count()
                
                if total_spots > 0:
                    availability_percentage = ((total_spots - occupied_spots) / total_spots) * 100
                    updated_lots.append({
                        'lot_id': lot.id,
                        'lot_name': lot.lot_name,
                        'total_spots': total_spots,
                        'occupied_spots': occupied_spots,
                        'availability_percentage': round(availability_percentage, 2)
                    })
            
            return {
                'status': 'success',
                'updated_lots': updated_lots,
                'total_lots_checked': len(lots)
            }
            
        except Exception as e:
            print(f"❌ Error checking parking lot availability: {str(e)}")
            return {'status': 'failed', 'message': str(e)}

@celery.task(bind=True)
def cleanup_old_records(self):
   
    flask_app = get_flask_app()
    with flask_app.app_context():
        try:
            cutoff_date = datetime.now() - timedelta(days=365)
            
            old_records = ParkingRecord.query.filter(
                ParkingRecord.parked_at < cutoff_date,
                ParkingRecord.left_at != None  # Only completed bookings
            ).all()
            
            deleted_count = len(old_records)
            
            for record in old_records:
                db.session.delete(record)
            
            db.session.commit()
            print(f"✅ Cleaned up {deleted_count} old parking records")
            
            return {
                'status': 'success',
                'deleted_count': deleted_count,
                'cutoff_date': cutoff_date.strftime('%Y-%m-%d')
            }
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error cleaning up old records: {str(e)}")
            return {'status': 'failed', 'message': str(e)}

@celery.task(bind=True)
def send_parking_reminder_notification(self, user_id, message):
    
    flask_app = get_flask_app()
    with flask_app.app_context():
        try:
            user = User.query.get(user_id)
            if not user or not user.email:
                return {'status': 'failed', 'message': 'User not found or no email'}
            
            subject = "🚗 Parking Reminder"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Parking Reminder</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #007bff; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .footer {{ text-align: center; color: #666; margin-top: 30px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🚗 Parking Reminder</h1>
                    </div>
                    
                    <div class="content">
                        <h2>Hello {user.fullname or user.username}!</h2>
                        <p>{message}</p>
                    </div>
                    
                    <div class="footer">
                        <p>Parking Management System</p>
                        <p>📧 Sent on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            result = send_email_task.delay(
                to=user.email,
                subject=subject,
                body=message,
                html_body=html_content
            )
            
            return {
                'status': 'success',
                'message': f'Reminder sent to {user.email}'
            }
            
        except Exception as e:
            print(f"❌ Error sending parking reminder: {str(e)}")
            return {'status': 'failed', 'message': str(e)}
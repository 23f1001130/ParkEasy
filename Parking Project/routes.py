import csv
import io
from flask import Blueprint, make_response, request, jsonify, session, render_template, redirect, url_for, flash
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from models import ParkingRecord, db, User, Admin, ParkingLot, ParkingSpot, Reservation
from datetime import datetime, timedelta
from functools import wraps
from tasks import send_instant_new_lot_email, generate_monthly_report, send_all_monthly_reports, export_user_parking_csv
from celery.result import AsyncResult
from extensions import cache

main = Blueprint('main', __name__)

def login_required(role='user'):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                if request.is_json or request.headers.get('Content-Type') == 'application/json':
                    return jsonify({'error': 'Login required'}), 401
                return redirect('/')
            
            if role == 'admin' and not session.get('is_admin'):
                if request.is_json or request.headers.get('Content-Type') == 'application/json':
                    return jsonify({'error': 'Admin access required'}), 403
                return redirect('/')
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

@main.route('/', methods=['GET'])
def show_login_form():
    return render_template('Login.html')

@main.route('/register', methods=['GET'])
def show_register_form():
    return render_template('Register.html')

@main.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        username = data.get('username')
        password = data.get('password')
        fullname = data.get('fullname')
        address = data.get('address')
        pincode = data.get('pincode')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400

        if len(username.strip()) < 3:
            return jsonify({'error': 'Username must be at least 3 characters long'}), 400
            
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({'error': 'Username already taken'}), 409

        email = f"{username}"
        
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            import random
            email = f"{username}_{random.randint(1000,9999)}"

        new_user = User(
            username=username.strip(),
            password=generate_password_hash(password),
            email=email,
            fullname=fullname.strip() if fullname else '',
            address=address.strip() if address else '',
            pincode=pincode.strip() if pincode else ''
        )

        db.session.add(new_user)
        db.session.commit()

        session['user_id'] = new_user.id
        session['is_admin'] = False

        return jsonify({
            'message': 'Registration successful! Redirecting to dashboard...',
            'success': True,
            'redirect_url': '/user/dashboard'
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Registration failed. Please try again.'}), 500

@main.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not all(k in data for k in ('username', 'password')):
        return jsonify({'error': 'Missing fields'}), 400

    user = User.query.filter_by(username=data['username']).first()
    if user and check_password_hash(user.password, data['password']):
        session['user_id'] = user.id
        session['is_admin'] = False
        return jsonify({'message': 'User login successful', 'is_admin': False}), 200

    admin = Admin.query.filter_by(username=data['username']).first()
    if admin and check_password_hash(admin.password, data['password']):
        session['user_id'] = admin.id
        session['is_admin'] = True
        return jsonify({'message': 'Admin login successful', 'is_admin': True}), 200

    return jsonify({'error': 'Invalid credentials'}), 401

@main.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    
    if request.method == 'GET':
        return redirect('/')
    else:
        return jsonify({'message': 'Logged out successfully'}), 200

@main.route("/admin/dashboard")
@login_required(role='admin')
def dashboard():
    return render_template("admin_dashboard.html")

@main.route('/admin/profile-page')
@login_required(role='admin')
def admin_profile_page():
    return render_template('Admin.html')

@main.route('/admin/profile', methods=['GET'])
@login_required(role='admin')
def get_admin_profile():
    try:
        admin = Admin.query.first()
        if not admin:
            return jsonify({'error': 'Admin not found'}), 404
            
        is_default = check_password_hash(admin.password, "admin123")
        
        profile_data = {
            'id': admin.id,
            'username': admin.username,
            'created_at': admin.created_at.isoformat() if hasattr(admin, 'created_at') else None,
            'is_default_password': is_default
        }
        
        return jsonify(profile_data)
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch profile'}), 500

@main.route('/admin/change-password', methods=['POST'])
@login_required(role='admin')
def change_admin_password():
    try:
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        if not all([current_password, new_password, confirm_password]):
            return jsonify({'error': 'All fields are required'}), 400
            
        admin = Admin.query.first()
        if not admin:
            return jsonify({'error': 'Admin not found'}), 404
            
        if not check_password_hash(admin.password, current_password):
            return jsonify({'error': 'Current password is incorrect'}), 400
            
        if new_password != confirm_password:
            return jsonify({'error': 'New passwords do not match'}), 400
            
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400
            
        admin.password = generate_password_hash(new_password)
        db.session.commit()
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to change password'}), 500

@main.route('/admin/change-username', methods=['POST'])
@login_required(role='admin')
def change_admin_username():
    try:
        data = request.get_json()
        new_username = data.get('new_username')
        
        if not new_username or not new_username.strip():
            return jsonify({'error': 'Username is required'}), 400
            
        new_username = new_username.strip()
        
        if len(new_username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters long'}), 400
            
        admin = Admin.query.first()
        if not admin:
            return jsonify({'error': 'Admin not found'}), 404
            
        admin.username = new_username
        db.session.commit()
        
        return jsonify({'message': 'Username changed successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to change username'}), 500

@main.route('/admin/summary')
@login_required(role='admin')
def admin_summary():
    return render_template('Admin_Summary.html')

@main.route('/api/admin/summary', methods=['GET'])
@login_required(role='admin')
def get_admin_summary():
    try:
        from sqlalchemy import func, case
        
        lot_revenue_query = db.session.query(
            ParkingLot.lot_name.label('lot_name'),
            func.coalesce(func.sum(ParkingRecord.parking_cost), 0).label('total_revenue'),
            func.count(ParkingRecord.id).label('total_bookings')
        ).outerjoin(
            ParkingSpot, ParkingLot.id == ParkingSpot.lot_id
        ).outerjoin(
            ParkingRecord, ParkingSpot.id == ParkingRecord.spot_id
        ).group_by(
            ParkingLot.id, ParkingLot.lot_name
        ).order_by(
            func.coalesce(func.sum(ParkingRecord.parking_cost), 0).desc()
        ).all()
        
        lot_occupancy_query = db.session.query(
            ParkingLot.lot_name.label('lot_name'),
            ParkingLot.number_of_spots.label('total_spots'),
            func.count(ParkingSpot.id).label('created_spots'),
            func.sum(
                case(
                    (ParkingSpot.status == 'O', 1),
                    else_=0
                )
            ).label('occupied_spots')
        ).outerjoin(
            ParkingSpot, ParkingLot.id == ParkingSpot.lot_id
        ).group_by(
            ParkingLot.id, ParkingLot.lot_name, ParkingLot.number_of_spots
        ).all()
        
        revenue_labels = []
        revenue_amounts = []
        
        for record in lot_revenue_query:
            lot_name = record.lot_name
            revenue = float(record.total_revenue or 0)
            
            if len(lot_name) > 20:
                lot_name = lot_name[:17] + "..."
            
            revenue_labels.append(lot_name)
            revenue_amounts.append(revenue)
        
        total_available_spots = 0
        total_occupied_spots = 0
        
        for record in lot_occupancy_query:
            occupied = int(record.occupied_spots or 0)
            created = int(record.created_spots or 0)
            available = created - occupied
            
            total_occupied_spots += occupied
            total_available_spots += available
        
        occupancy_labels = []
        occupancy_data = []
        
        if total_available_spots > 0 or total_occupied_spots > 0:
            occupancy_labels = ['Available Spots', 'Occupied Spots']
            occupancy_data = [total_available_spots, total_occupied_spots]
        
        total_revenue = sum(revenue_amounts)
        total_lots = len(lot_revenue_query)
        total_spots = total_available_spots + total_occupied_spots
        
        try:
            total_bookings = db.session.query(func.count(ParkingRecord.id)).filter(
                ParkingRecord.parking_cost.isnot(None)
            ).scalar() or 0
        except Exception as e:
            total_bookings = 0
        
        response_data = {
            'success': True,
            'data': {
                'revenue': {
                    'labels': revenue_labels,
                    'amounts': revenue_amounts
                },
                'occupancy': {
                    'labels': occupancy_labels,
                    'counts': occupancy_data
                }
            },
            'metadata': {
                'period': 'All Time',
                'total_revenue': round(total_revenue, 2),
                'total_bookings': total_bookings,
                'total_lots': total_lots,
                'total_spots': total_spots,
                'available_spots': total_available_spots,
                'occupied_spots': total_occupied_spots,
                'occupancy_rate': round((total_occupied_spots / total_spots * 100), 1) if total_spots > 0 else 0
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to load admin summary data: {str(e)}',
            'data': {
                'revenue': {'labels': [], 'amounts': []},
                'occupancy': {'labels': [], 'counts': []}
            },
            'metadata': {
                'period': 'Error',
                'total_revenue': 0,
                'total_bookings': 0,
                'total_lots': 0,
                'total_spots': 0,
                'available_spots': 0,
                'occupied_spots': 0,
                'occupancy_rate': 0
            }
        }), 500

@main.route('/admin/users')
@login_required()
def admin_users_page():
    try:
        admin_id = session.get('admin_id') or session.get('user_id')
        
        if not admin_id:
            session.clear()
            return redirect('/admin/login')
        
        return render_template('users.html')
        
    except Exception as e:
        return f"Error: {str(e)}", 500

@main.route('/admin/users/list')
@login_required()
def get_users_list():
    try:
        admin_id = session.get('admin_id') or session.get('user_id')
        
        if not admin_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        users = User.query.order_by(User.created_on.asc()).all()
        
        from datetime import datetime, timedelta, date
        
        now = datetime.now()
        today = now.date()
        
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        week_ago = now - timedelta(days=7)
        
        total_users = len(users)
        today_registrations = 0
        week_registrations = 0
        
        for user in users:
            if user.created_on:
                user_date = user.created_on
                
                if today_start <= user_date <= today_end:
                    today_registrations += 1
                
                if user_date >= week_ago:
                    week_registrations += 1
        
        users_list = []
        for user in users:
            user_dict = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.fullname,
                'address': user.address,
                'pincode': user.pincode,
                'preferred_contact': user.preferred_contact,
                'created_at': user.created_on.isoformat() if user.created_on else None
            }
            users_list.append(user_dict)
        
        response_data = {
            'users': users_list,
            'statistics': {
                'total_users': total_users,
                'today_registrations': today_registrations,
                'week_registrations': week_registrations
            }
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main.route('/admin/lots', methods=['GET', 'POST'])
@login_required(role='admin')
def manage_lots():
    if request.method == 'GET':
        lots = ParkingLot.query.filter_by(is_active=True).all()
        result = []
        for lot in lots:
            spots = ParkingSpot.query.filter_by(lot_id=lot.id, is_active=True).all()
            total_spots = len(spots)
            occupied_spots = len([s for s in spots if s.status == 'O'])

            spots_data = []
            for spot in spots:
                spot_data = {
                    'id': spot.id,
                    'spot_number': spot.spot_number,
                    'status': spot.status,
                    'is_reserved': spot.status == 'O'
                }
                
                if spot.status == 'O':
                    current_record = ParkingRecord.query.filter_by(
                        spot_id=spot.id, 
                        left_at=None
                    ).first()
                    
                    spot_data.update({
                        'vehicle_no': current_record.vehicle_number,
                        'user_name': current_record.user.username if current_record.user else 'Unknown',
                        'timestamp': current_record.parked_at.isoformat() if current_record.parked_at else None
                    })
                
                spots_data.append(spot_data)

            result.append({
                'id': lot.id,
                'lot_name': lot.lot_name,
                'address': lot.address,
                'pincode': lot.pincode,
                'price_per_hour': lot.price_per_hour,
                'number_of_spots': lot.number_of_spots,
                'total_spots': total_spots,
                'occupied_spots': occupied_spots,
                'available_spots': total_spots - occupied_spots,
                'spots': spots_data
            })
        
        return jsonify(result)

    try:
        data = request.get_json()

        required_fields = ['lot_name', 'address', 'pincode', 'price_per_hour', 'number_of_spots']
        if not all(k in data for k in required_fields):
            missing = [k for k in required_fields if k not in data]
            return jsonify({'error': f'Missing fields: {missing}'}), 400

        lot = ParkingLot(
            lot_name=data['lot_name'],
            address=data['address'],
            pincode=data['pincode'],
            price_per_hour=float(data['price_per_hour']),
            number_of_spots=int(data['number_of_spots']),
            is_active=True
        )

        db.session.add(lot)
        db.session.flush()

        for i in range(1, int(data['number_of_spots']) + 1):
            spot = ParkingSpot(
                spot_number=str(i),
                lot_id=lot.id,
                status='A',
                is_active=True
            )
            db.session.add(spot)

        db.session.commit()

        try:
            task = send_instant_new_lot_email.delay(lot.id)
            email_status = "Users are being notified via email!"
        except Exception as email_error:
            email_status = "Parking lot created (email notification task failed)"

        response_data = {
            'id': lot.id,
            'lot_name': lot.lot_name,
            'address': lot.address,
            'pincode': lot.pincode,
            'price_per_hour': lot.price_per_hour,
            'number_of_spots': lot.number_of_spots,
            'message': f'New parking lot added successfully - {email_status}'
        }

        return jsonify(response_data), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create parking lot: {str(e)}'}), 500

@main.route('/admin/reports/monthly', methods=['GET'])
@login_required(role='admin')
def admin_monthly_reports_page():
    return render_template('admin_monthly_reports.html')

@main.route('/admin/reports/monthly/trigger', methods=['POST'])
@login_required(role='admin')
def trigger_monthly_reports():
    try:
        task = send_all_monthly_reports.delay()
        
        return jsonify({
            'success': True,
            'message': 'Monthly reports are being generated and sent to all users',
            'task_id': task.id
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to trigger monthly reports: {str(e)}'
        }), 500

@main.route('/admin/reports/monthly/user/<int:user_id>', methods=['POST'])
@login_required(role='admin')
def trigger_user_monthly_report(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        task = generate_monthly_report.delay(user_id)
        
        return jsonify({
            'success': True,
            'message': f'Monthly report is being generated for {user.username}',
            'task_id': task.id
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to trigger monthly report: {str(e)}'
        }), 500

@main.route('/api/user/request-monthly-report', methods=['POST'])
@login_required()
def request_monthly_report():
    try:
        user_id = session['user_id']
        
        task = generate_monthly_report.delay(user_id)
        
        return jsonify({
            'success': True,
            'message': 'Your monthly report is being generated and will be sent to your email shortly',
            'task_id': task.id
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Failed to generate monthly report. Please try again.'
        }), 500

@main.route('/admin/lots/<int:lot_id>', methods=['PUT'])
@login_required(role='admin')
def update_lot(lot_id):
    try:
        lot = ParkingLot.query.get_or_404(lot_id)
        data = request.get_json()

        required_fields = ['lot_name', 'address', 'pincode', 'price_per_hour', 'number_of_spots']
        if not all(k in data for k in required_fields):
            missing = [k for k in required_fields if k not in data]
            return jsonify({'error': f'Missing fields: {missing}'}), 400

        lot.lot_name = data['lot_name']
        lot.address = data['address']
        lot.pincode = data['pincode']
        lot.price_per_hour = float(data['price_per_hour'])
        
        new_spot_count = int(data['number_of_spots'])
        current_spots = ParkingSpot.query.filter_by(lot_id=lot_id, is_active=True).all()
        current_spot_count = len(current_spots)
        
        if new_spot_count != current_spot_count:
            occupied_spots = [s for s in current_spots if s.status == 'O']
            if occupied_spots and new_spot_count < current_spot_count:
                return jsonify({'error': 'Cannot reduce spots while some are occupied'}), 400
            
            if new_spot_count > current_spot_count:
                for i in range(current_spot_count + 1, new_spot_count + 1):
                    new_spot = ParkingSpot(
                        spot_number=str(i),
                        lot_id=lot_id,
                        status='A',
                        is_active=True
                    )
                    db.session.add(new_spot)
            elif new_spot_count < current_spot_count:
                spots_to_remove = current_spots[new_spot_count:]
                for spot in spots_to_remove:
                    if spot.status == 'O':
                        return jsonify({'error': f'Cannot remove occupied spot {spot.spot_number}'}), 400
                    spot.is_active = False
        
        lot.number_of_spots = new_spot_count
        db.session.commit()
        
        return jsonify({
            'id': lot.id,
            'lot_name': lot.lot_name,
            'address': lot.address,
            'pincode': lot.pincode,
            'price_per_hour': lot.price_per_hour,
            'number_of_spots': lot.number_of_spots,
            'message': 'Parking lot updated successfully'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to update parking lot: {str(e)}'}), 500

@main.route('/admin/lots/<int:lot_id>', methods=['DELETE'])
@login_required(role='admin')
def delete_lot(lot_id):
    try:
        lot = ParkingLot.query.get_or_404(lot_id)
        
        occupied_spots = ParkingSpot.query.filter_by(
            lot_id=lot_id, 
            status='O', 
            is_active=True
        ).all()
        
        if occupied_spots:
            return jsonify({
                'error': f'Cannot delete lot. {len(occupied_spots)} spots are currently occupied.'
            }), 400
        
        lot.is_active = False
        spots = ParkingSpot.query.filter_by(lot_id=lot_id).all()
        for spot in spots:
            spot.is_active = False
        
        db.session.commit()
        
        return jsonify({'message': 'Parking lot deleted successfully'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete parking lot: {str(e)}'}), 500

@main.route('/admin/spots/<int:lot_id>', methods=['GET'])
@login_required(role='admin')
def view_spots(lot_id):
    try:
        spots = ParkingSpot.query.filter_by(lot_id=lot_id, is_active=True).all()
        spots_data = []
        
        for spot in spots:
            spot_data = {
                'id': spot.id,
                'spot_number': spot.spot_number,
                'status': spot.status,
                'is_reserved': spot.status == 'O'
            }
            
            if spot.status == 'O':
                current_record = ParkingRecord.query.filter_by(
                    spot_id=spot.id, 
                    left_at=None
                ).first()
                
                if current_record:
                    spot_data.update({
                        'vehicle_no': current_record.vehicle_number,
                        'user_name': current_record.user.username if current_record.user else 'Unknown',
                        'timestamp': current_record.parked_at.isoformat() if current_record.parked_at else None
                    })
            
            spots_data.append(spot_data)
            
        return jsonify(spots_data)
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch spots'}), 500

@main.route('/user')
@login_required()
def user_redirect():
    return redirect(url_for('main.user_dashboard'))

@main.route('/user/dashboard')
@login_required()
def user_dashboard():
    try:
        user_id = session['user_id']
        current_user = User.query.get(user_id)
        
        if not current_user:
            session.clear()
            return redirect('/')
        
        return render_template('User_Dashboard.html', current_user=current_user)
        
    except Exception as e:
        return f"Error: {str(e)}", 500

@main.route('/user/profile')
@login_required()
def user_profile():
    user_id = session['user_id']
    current_user = User.query.get(user_id)
    
    if not current_user:
        session.clear()
        return redirect('/')
    
    return render_template('User_Profile.html', current_user=current_user)

@main.route('/user/summary')
@login_required()
def user_booking_history():
    user_id = session['user_id']
    current_user = User.query.get(user_id)
    
    if not current_user:
        session.clear()
        return redirect('/')
    
    return render_template('User_Summary.html', current_user=current_user)

@main.route('/user/search-parking')
@login_required()
def user_search_parking():
    user_id = session['user_id']
    current_user = User.query.get(user_id)
    
    if not current_user:
        session.clear()
        return redirect('/')
    
    return render_template('User_Search_Parking.html', current_user=current_user)

@main.route('/api/user/dashboard', methods=['GET'])
@login_required()
def get_user_dashboard_data():
    try:
        user_id = session['user_id']
        
        cache_key = f"user_dashboard_{user_id}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return jsonify(cached_data)
        
        recent_bookings = db.session.query(ParkingRecord).join(
            ParkingSpot, ParkingRecord.spot_id == ParkingSpot.id
        ).join(
            ParkingLot, ParkingSpot.lot_id == ParkingLot.id
        ).filter(
            ParkingRecord.user_id == user_id
        ).order_by(
            ParkingRecord.parked_at.desc()
        ).limit(10).all()
        
        recent_bookings_data = []
        for booking in recent_bookings:
            recent_bookings_data.append({
                'id': booking.id,
                'location': booking.spot.lot.lot_name,
                'vehicle_number': booking.vehicle_number,
                'timestamp': booking.parked_at.isoformat(),
                'completed': booking.left_at is not None,
                'spot_id': booking.spot_id
            })
        
        current_booking = ParkingRecord.query.join(
            ParkingSpot, ParkingRecord.spot_id == ParkingSpot.id
        ).join(
            ParkingLot, ParkingSpot.lot_id == ParkingLot.id
        ).filter(
            ParkingRecord.user_id == user_id,
            ParkingRecord.left_at == None
        ).first()
        
        current_booking_data = None
        if current_booking:
            current_booking_data = {
                'id': current_booking.id,
                'spot_id': current_booking.spot_id,
                'location': current_booking.spot.lot.lot_name,
                'vehicle_number': current_booking.vehicle_number,
                'timestamp': current_booking.parked_at.isoformat()
            }
        
        dashboard_data = {
            'recent_bookings': recent_bookings_data,
            'current_booking': current_booking_data
        }
        
        cache.set(cache_key, dashboard_data, timeout=180)
        
        return jsonify(dashboard_data)
        
    except Exception as e:
        return jsonify({'error': 'Failed to load dashboard data'}), 500

def clear_user_cache(user_id):
    try:
        cache_key = f"user_dashboard_{user_id}"
        cache.delete(cache_key)
    except Exception as e:
        pass

@main.route('/api/user/daily-summary', methods=['GET'])
@login_required()
def get_daily_summary():
    try:
        user_id = session['user_id']
        
        from datetime import datetime, timedelta
        from sqlalchemy import func
        
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=29)
        
        daily_data = db.session.query(
            func.date(ParkingRecord.parked_at).label('date'),
            func.count(ParkingRecord.id).label('booking_count'),
            func.sum(ParkingRecord.parking_cost).label('total_spent')
        ).filter(
            ParkingRecord.user_id == user_id,
            ParkingRecord.parked_at.isnot(None),
            func.date(ParkingRecord.parked_at) >= start_date,
            func.date(ParkingRecord.parked_at) <= end_date
        ).group_by(
            func.date(ParkingRecord.parked_at)
        ).order_by(
            func.date(ParkingRecord.parked_at)
        ).all()
        
        labels = []
        bookings = []
        spending = []
        
        data_dict = {}
        for record in daily_data:
            date_str = str(record.date)
            data_dict[date_str] = {
                'bookings': int(record.booking_count),
                'spending': float(record.total_spent or 0)
            }
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            labels.append(date_str)
            
            if date_str in data_dict:
                bookings.append(data_dict[date_str]['bookings'])
                spending.append(data_dict[date_str]['spending'])
            else:
                bookings.append(0)
                spending.append(0.0)
            
            current_date += timedelta(days=1)
        
        response_data = {
            'success': True,
            'data': {
                'labels': labels,
                'bookings': bookings,
                'spending': spending
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to load daily summary: {str(e)}',
            'data': {
                'labels': [],
                'bookings': [],
                'spending': []
            }
        }), 500

@main.route('/api/user/parking-history', methods=['GET'])
@login_required()
def get_user_parking_history():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'User not authenticated'}), 401
        
        user_id = session['user_id']
        from sqlalchemy import func
        
        history = db.session.query(
            ParkingRecord.id,
            ParkingRecord.vehicle_number,
            ParkingRecord.parked_at,
            ParkingRecord.left_at,
            ParkingRecord.parking_cost,
            ParkingRecord.remarks,
            ParkingSpot.spot_number,
            ParkingLot.lot_name,
            ParkingLot.address
        ).join(
            ParkingSpot, ParkingRecord.spot_id == ParkingSpot.id
        ).join(
            ParkingLot, ParkingSpot.lot_id == ParkingLot.id
        ).filter(
            ParkingRecord.user_id == user_id
        ).order_by(
            ParkingRecord.parked_at.desc()
        ).limit(50).all()
        
        history_data = []
        for record in history:
            history_data.append({
                'id': record.id,
                'vehicle_number': record.vehicle_number,
                'parked_at': str(record.parked_at),
                'left_at': str(record.left_at) if record.left_at else 'Still parked',
                'parking_cost': float(record.parking_cost or 0),
                'remarks': record.remarks,
                'spot_number': record.spot_number,
                'lot_name': record.lot_name,
                'lot_address': record.address,
                'duration': str(record.left_at - record.parked_at) if record.left_at else 'Ongoing'
            })
        
        return jsonify({
            'success': True,
            'history': history_data,
            'total_records': len(history_data)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main.route('/api/user/stats', methods=['GET'])
@login_required()
def get_user_stats():
    try:
        user_id = session['user_id']
        
        total_bookings = ParkingRecord.query.filter_by(user_id=user_id).count()
        active_count = ParkingRecord.query.filter_by(user_id=user_id, left_at=None).count()
        
        total_spent = db.session.query(func.sum(ParkingRecord.parking_cost)).filter(
            ParkingRecord.user_id == user_id,
            ParkingRecord.parking_cost != None
        ).scalar() or 0.0
        
        return jsonify({
            'success': True,
            'totalBookings': total_bookings,
            'totalSpent': round(float(total_spent), 2),
            'activeCount': active_count
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Failed to load stats',
            'totalBookings': 0,
            'totalSpent': 0,
            'activeCount': 0
        }), 500

@main.route('/api/user/profile', methods=['GET'])
@login_required()
def get_user_profile():
    try:
        user_id = session['user_id']
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        profile_data = {
            'username': user.username,
            'email': getattr(user, 'email', ''),
            'phone': getattr(user, 'phone', ''),
            'date_of_birth': getattr(user, 'date_of_birth', ''),
            'address': getattr(user, 'address', ''),
            'city': getattr(user, 'city', ''),
            'pincode': getattr(user, 'pincode', ''),
            'primary_vehicle': getattr(user, 'primary_vehicle', ''),
            'vehicle_type': getattr(user, 'vehicle_type', '')
        }
        
        return jsonify({'profile': profile_data})
        
    except Exception as e:
        return jsonify({'error': 'Failed to load profile'}), 500

@main.route('/api/user/profile', methods=['PUT'])
@login_required()
def update_user_profile():
    try:
        user_id = session['user_id']
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.username = data.get('username', user.username)
        
        if hasattr(user, 'email'):
            user.email = data.get('email', user.email)
        if hasattr(user, 'phone'):
            user.phone = data.get('phone', user.phone)
        if hasattr(user, 'address'):
            user.address = data.get('address', user.address)
        if hasattr(user, 'city'):
            user.city = data.get('city', user.city)
        if hasattr(user, 'pincode'):
            user.pincode = data.get('pincode', user.pincode)
        if hasattr(user, 'primary_vehicle'):
            user.primary_vehicle = data.get('primary_vehicle', user.primary_vehicle)
        if hasattr(user, 'vehicle_type'):
            user.vehicle_type = data.get('vehicle_type', user.vehicle_type)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Profile updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update profile'}), 500

@main.route('/api/user/change-password', methods=['POST'])
@login_required()
def change_user_password():
    try:
        user_id = session['user_id']
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not check_password_hash(user.password, current_password):
            return jsonify({'error': 'Current password is incorrect'}), 400
        
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400
        
        user.password = generate_password_hash(new_password)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Password changed successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to change password'}), 500

@main.route('/api/parking-lots/search', methods=['GET'])
@login_required()
def search_parking_lots():
    try:
        query = request.args.get('q', '').strip()
        
        if not query:
            lots = ParkingLot.query.filter_by(is_active=True).all()
        else:
            lots = ParkingLot.query.filter(
                ParkingLot.is_active == True,
                db.or_(
                    ParkingLot.lot_name.ilike(f'%{query}%'),
                    ParkingLot.address.ilike(f'%{query}%'),
                    ParkingLot.pincode.ilike(f'%{query}%')
                )
            ).all()
        
        results = []
        for lot in lots:
            total_spots = ParkingSpot.query.filter_by(lot_id=lot.id, is_active=True).count()
            occupied_spots = ParkingSpot.query.filter_by(lot_id=lot.id, status='O', is_active=True).count()
            available_spots = total_spots - occupied_spots
            
            results.append({
                'id': lot.id,
                'name': lot.lot_name,
                'location': lot.address,
                'address': lot.address,
                'pincode': lot.pincode,
                'cost_per_hour': float(lot.price_per_hour),
                'price_per_hour': float(lot.price_per_hour),
                'available_spots': available_spots,
                'total_spots': total_spots
            })
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Failed to search parking lots',
            'results': []
        }), 500

@main.route('/api/parking-lots/all', methods=['GET'])
@login_required()
def get_all_parking_lots():
    try:
        lots = ParkingLot.query.filter_by(is_active=True).all()
        
        results = []
        for lot in lots:
            total_spots = ParkingSpot.query.filter_by(lot_id=lot.id, is_active=True).count()
            occupied_spots = ParkingSpot.query.filter_by(lot_id=lot.id, status='O', is_active=True).count()
            available_spots = total_spots - occupied_spots
            
            results.append({
                'id': lot.id,
                'name': lot.lot_name,
                'location': lot.address,
                'address': lot.address,
                'pincode': lot.pincode,
                'cost_per_hour': float(lot.price_per_hour),
                'price_per_hour': float(lot.price_per_hour),
                'available_spots': available_spots,
                'total_spots': total_spots
            })
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Failed to load parking lots',
            'results': []
        }), 500

@main.route('/api/parking-lots/<int:lot_id>', methods=['GET'])
@login_required()
def get_parking_lot_details(lot_id):
    try:
        lot = ParkingLot.query.filter_by(id=lot_id, is_active=True).first()
        
        if not lot:
            return jsonify({
                'success': False,
                'error': 'Parking lot not found'
            }), 404
        
        total_spots = ParkingSpot.query.filter_by(lot_id=lot.id, is_active=True).count()
        occupied_spots = ParkingSpot.query.filter_by(lot_id=lot.id, status='O', is_active=True).count()
        available_spots = total_spots - occupied_spots
        
        return jsonify({
            'success': True,
            'lot': {
                'id': lot.id,
                'name': lot.lot_name,
                'location': lot.address,
                'address': lot.address,
                'pincode': lot.pincode,
                'cost_per_hour': float(lot.price_per_hour),
                'price_per_hour': float(lot.price_per_hour),
                'available_spots': available_spots,
                'total_spots': total_spots
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Failed to load parking lot details'
        }), 500

@main.route('/api/user/book', methods=['POST'])
@login_required()
def book_parking():
    try:
        data = request.get_json()
        user_id = session['user_id']
        lot_id = data.get('lot_id')
        vehicle_number = data.get('vehicle_number', '').strip().upper()
        
        if not lot_id:
            return jsonify({
                'success': False, 
                'message': 'Parking lot ID is required'
            }), 400
            
        if not vehicle_number or len(vehicle_number) < 3:
            return jsonify({
                'success': False, 
                'message': 'Please enter a valid vehicle number (minimum 3 characters)'
            }), 400
        
        active_booking = ParkingRecord.query.filter_by(
            user_id=user_id,
            left_at=None
        ).first()
        
        if active_booking:
            return jsonify({
                'success': False, 
                'message': 'You already have an active booking. Please release it first.'
            }), 400
        
        lot = ParkingLot.query.filter_by(id=lot_id, is_active=True).first()
        if not lot:
            return jsonify({
                'success': False, 
                'message': 'Selected parking lot is not available'
            }), 400
        
        available_spot = ParkingSpot.query.filter_by(
            lot_id=lot_id,
            status='A',
            is_active=True
        ).first()
        
        if not available_spot:
            return jsonify({
                'success': False, 
                'message': 'No available spots in this parking lot'
            }), 400
        
        parking_record = ParkingRecord(
            user_id=user_id,
            spot_id=available_spot.id,
            vehicle_number=vehicle_number,
            parked_at=datetime.now(),
            parking_cost=0.0
        )
        
        available_spot.status = 'O'
        
        db.session.add(parking_record)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Parking spot booked successfully!',
            'booking': {
                'id': parking_record.id,
                'spot_number': available_spot.spot_number,
                'location': lot.lot_name,
                'vehicle_number': vehicle_number,
                'booked_at': parking_record.parked_at.isoformat(),
                'cost_per_hour': float(lot.price_per_hour)
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False, 
            'message': 'Failed to book parking spot. Please try again.'
        }), 500

@main.route('/api/user/release', methods=['POST'])
@login_required()
def release_parking():
    try:
        data = request.get_json()
        user_id = session['user_id']
        booking_id = data.get('booking_id')
        
        if not booking_id:
            return jsonify({
                'success': False, 
                'message': 'Booking ID is required'
            }), 400
        
        parking_record = ParkingRecord.query.filter_by(
            id=booking_id,
            user_id=user_id,
            left_at=None
        ).first()
        
        if not parking_record:
            return jsonify({
                'success': False, 
                'message': 'No active booking found or booking already released'
            }), 400
        
        now = datetime.now()
        parking_duration = now - parking_record.parked_at
        hours = max(0.1, parking_duration.total_seconds() / 3600)
        lot = parking_record.spot.lot
        total_cost = round(hours * float(lot.price_per_hour), 2)
        
        parking_record.left_at = now
        parking_record.parking_cost = total_cost
        parking_record.spot.status = 'A'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Parking released successfully! Total cost: ₹{total_cost}',
            'release_details': {
                'total_cost': total_cost,
                'duration_hours': round(hours, 2),
                'released_at': now.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False, 
            'message': 'Failed to release parking spot. Please try again.'
        }), 500

@main.route('/api/user/bookings', methods=['GET'])
@login_required()
def get_user_bookings():
    try:
        user_id = session['user_id']
        
        bookings = db.session.query(ParkingRecord).join(
            ParkingSpot, ParkingRecord.spot_id == ParkingSpot.id
        ).join(
            ParkingLot, ParkingSpot.lot_id == ParkingLot.id
        ).filter(
            ParkingRecord.user_id == user_id
        ).order_by(
            ParkingRecord.parked_at.desc()
        ).all()
        
        bookings_data = []
        for booking in bookings:
            total_cost = booking.parking_cost
            if booking.left_at and not total_cost:
                duration = booking.left_at - booking.parked_at
                hours = max(0.1, duration.total_seconds() / 3600)
                total_cost = round(hours * float(booking.spot.lot.price_per_hour), 2)
            
            bookings_data.append({
                'id': booking.id,
                'location': booking.spot.lot.lot_name,
                'vehicle_number': booking.vehicle_number,
                'parking_time': booking.parked_at.isoformat(),
                'releasing_time': booking.left_at.isoformat() if booking.left_at else None,
                'total_cost': float(total_cost) if total_cost else 0,
                'status': 'active' if booking.left_at is None else 'completed'
            })
        
        return jsonify({
            'success': True,
            'bookings': bookings_data,
            'count': len(bookings_data)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Failed to load bookings',
            'bookings': []
        }), 500

@main.route('/api/user/export-csv', methods=['POST'])
@login_required()
def export_csv():
    try:
        user_id = session['user_id']
        
        job = export_user_parking_csv.delay(user_id)
        
        return jsonify({
            'success': True,
            'message': 'CSV export started! You will receive an email when complete.',
            'job_id': job.id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to start export'
        }), 500

@main.route('/reserve/<int:spot_id>', methods=['POST'])
@login_required()
def reserve_spot(spot_id):
    spot = ParkingSpot.query.get(spot_id)
    if not spot:
        return jsonify({'error': 'Spot not found'}), 404

    if spot.is_reserved:
        return jsonify({'error': 'Spot already reserved'}), 400

    spot.is_reserved = True
    new_reservation = Reservation(
        user_id=session['user_id'],
        spot_id=spot.id,
        reserved_at=datetime.now()
    )
    db.session.add(new_reservation)
    db.session.commit()

    return jsonify({'message': 'Spot reserved successfully'})

@main.route('/release/<int:spot_id>', methods=['POST'])
@login_required()
def release_spot(spot_id):
    spot = ParkingSpot.query.get(spot_id)
    if not spot or not spot.is_reserved:
        return jsonify({'error': 'Spot not currently reserved'}), 404

    reservation = Reservation.query.filter_by(spot_id=spot.id, user_id=session['user_id'], released_at=None).first()
    if not reservation:
        return jsonify({'error': 'No active reservation found for you'}), 400

    spot.is_reserved = False
    reservation.released_at = datetime.now()

    db.session.commit()

    return jsonify({'message': 'Spot released successfully'})
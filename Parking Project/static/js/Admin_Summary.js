const { createApp, ref, computed, onMounted, nextTick } = Vue;

createApp({
    setup() {
        const loading = ref(true);
        const errorMessage = ref('');
        const summaryData = ref({
            revenue: { labels: [], amounts: [] },
            occupancy: { labels: [], counts: [] }
        });
        const metadata = ref({
            period: 'Loading...',
            total_revenue: 0,
            total_bookings: 0,
            total_lots: 0,
            available_spots: 0,
            occupied_spots: 0,
            occupancy_rate: 0
        });

        let revenueChart = null;
        let occupancyChart = null;

        // Computed properties - IMPROVED LOGIC
        const hasRevenueData = computed(() => {
            console.log('Checking revenue data:', summaryData.value.revenue);
            const hasLabels = summaryData.value.revenue.labels && summaryData.value.revenue.labels.length > 0;
            const hasAmounts = summaryData.value.revenue.amounts && summaryData.value.revenue.amounts.length > 0;
            const hasPositiveAmounts = summaryData.value.revenue.amounts && summaryData.value.revenue.amounts.some(amount => amount > 0);
            
            console.log('Revenue check:', { hasLabels, hasAmounts, hasPositiveAmounts });
            return hasLabels && hasAmounts && hasPositiveAmounts;
        });

        const hasOccupancyData = computed(() => {
            console.log('Checking occupancy data:', summaryData.value.occupancy);
            const hasLabels = summaryData.value.occupancy.labels && summaryData.value.occupancy.labels.length > 0;
            const hasCounts = summaryData.value.occupancy.counts && summaryData.value.occupancy.counts.length > 0;
            const hasPositiveCounts = summaryData.value.occupancy.counts && summaryData.value.occupancy.counts.some(count => count > 0);
            
            console.log('Occupancy check:', { hasLabels, hasCounts, hasPositiveCounts });
            return hasLabels && hasCounts && hasPositiveCounts;
        });

        // Load summary data from API
        const loadSummaryData = async () => {
            loading.value = true;
            errorMessage.value = '';

            try {
                console.log('Loading admin summary data...');
                const response = await axios.get('/api/admin/summary');
                console.log('Raw API response:', response.data);

                if (response.data && response.data.success) {
                    console.log('API returned success. Data:', response.data.data);
                    console.log('API returned metadata:', response.data.metadata);
                    
                    // Ensure data structure is correct
                    summaryData.value = {
                        revenue: {
                            labels: response.data.data.revenue.labels || [],
                            amounts: response.data.data.revenue.amounts || []
                        },
                        occupancy: {
                            labels: response.data.data.occupancy.labels || [],
                            counts: response.data.data.occupancy.counts || []
                        }
                    };
                    
                    metadata.value = response.data.metadata || {};
                    
                    console.log('Processed summary data:', summaryData.value);
                    console.log('Processed metadata:', metadata.value);

                    // Wait for Vue to update the DOM, then create charts
                    await nextTick();
                    
                    // Add delay to ensure DOM is ready
                    setTimeout(() => {
                        console.log('About to create charts...');
                        createCharts();
                    }, 100);
                } else {
                    errorMessage.value = response.data.error || response.data.message || 'Failed to load summary data';
                    console.error('API returned error:', response.data);
                }
            } catch (error) {
                console.error('Error loading summary data:', error);
                if (error.response) {
                    console.error('Error response:', error.response.data);
                    errorMessage.value = `Server Error: ${error.response.status} - ${error.response.data.error || 'Unknown error'}`;
                } else if (error.request) {
                    errorMessage.value = 'Network error: Unable to reach server';
                } else {
                    errorMessage.value = 'Error loading data';
                }
            } finally {
                loading.value = false;
            }
        };

        // Create both charts
        const createCharts = () => {
            console.log('Creating charts with data:', summaryData.value);
            console.log('hasRevenueData:', hasRevenueData.value);
            console.log('hasOccupancyData:', hasOccupancyData.value);

            // Check if Chart.js is loaded
            if (typeof Chart === 'undefined') {
                console.error('Chart.js is not loaded!');
                errorMessage.value = 'Chart library failed to load. Please refresh the page.';
                return;
            }

            // Destroy existing charts
            if (revenueChart) {
                revenueChart.destroy();
                revenueChart = null;
            }
            if (occupancyChart) {
                occupancyChart.destroy();
                occupancyChart = null;
            }

            // Chart 1: Revenue by Parking Lot (Bar Chart)
            const revenueCanvas = document.getElementById('revenueChart');
            if (!revenueCanvas) {
                console.error('Revenue chart canvas not found - DOM may not be ready yet');
                // Try again after a short delay
                setTimeout(() => {
                    createCharts();
                }, 200);
                return;
            }

            if (hasRevenueData.value) {
                console.log('Creating revenue chart with:', summaryData.value.revenue);
                try {
                    const revenueCtx = revenueCanvas.getContext('2d');
                    revenueChart = new Chart(revenueCtx, {
                        type: 'bar',
                        data: {
                            labels: summaryData.value.revenue.labels,
                            datasets: [{
                                label: 'Total Revenue (₹)',
                                data: summaryData.value.revenue.amounts,
                                backgroundColor: 'rgba(40, 167, 69, 0.8)',
                                borderColor: 'rgba(40, 167, 69, 1)',
                                borderWidth: 2,
                                borderRadius: 8,
                                borderSkipped: false,
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                title: {
                                    display: true,
                                    text: 'Total Earnings Since Parking Lot Creation',
                                    font: { size: 14, weight: 'bold' }
                                },
                                legend: { 
                                    display: true,
                                    position: 'top'
                                },
                                tooltip: {
                                    callbacks: {
                                        label: function(context) {
                                            return 'Revenue: ₹' + context.parsed.y.toLocaleString();
                                        }
                                    }
                                }
                            },
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    title: {
                                        display: true,
                                        text: 'Revenue (₹)'
                                    },
                                    ticks: {
                                        callback: function(value) {
                                            return '₹' + value.toLocaleString();
                                        }
                                    }
                                },
                                x: {
                                    title: {
                                        display: true,
                                        text: 'Parking Lots'
                                    },
                                    ticks: {
                                        maxRotation: 45
                                    }
                                }
                            }
                        }
                    });
                    console.log('Revenue chart created successfully');
                } catch (error) {
                    console.error('Error creating revenue chart:', error);
                    errorMessage.value = 'Failed to create revenue chart: ' + error.message;
                }
            } else {
                console.log('Revenue chart not created - no data available');
            }

            // Chart 2: Available vs Occupied Spots (Pie Chart)
            const occupancyCanvas = document.getElementById('occupancyChart');
            if (!occupancyCanvas) {
                console.error('Occupancy chart canvas not found');
                return;
            }

            if (hasOccupancyData.value) {
                console.log('Creating occupancy chart with:', summaryData.value.occupancy);
                try {
                    const occupancyCtx = occupancyCanvas.getContext('2d');
                    occupancyChart = new Chart(occupancyCtx, {
                        type: 'pie',
                        data: {
                            labels: summaryData.value.occupancy.labels,
                            datasets: [{
                                label: 'Parking Spots',
                                data: summaryData.value.occupancy.counts,
                                backgroundColor: [
                                    'rgba(40, 167, 69, 0.8)',    // Available - Green
                                    'rgba(220, 53, 69, 0.8)'     // Occupied - Red
                                ],
                                borderColor: [
                                    'rgba(40, 167, 69, 1)',
                                    'rgba(220, 53, 69, 1)'
                                ],
                                borderWidth: 2
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                title: {
                                    display: true,
                                    text: 'Current Parking Spot Status',
                                    font: { size: 14, weight: 'bold' }
                                },
                                legend: { 
                                    position: 'bottom',
                                    labels: {
                                        padding: 20,
                                        usePointStyle: true,
                                        font: {
                                            size: 12
                                        }
                                    }
                                },
                                tooltip: {
                                    callbacks: {
                                        label: function(context) {
                                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                            const percentage = ((context.parsed / total) * 100).toFixed(1);
                                            return context.label + ': ' + context.parsed + ' spots (' + percentage + '%)';
                                        }
                                    }
                                }
                            }
                        }
                    });
                    console.log('Occupancy chart created successfully');
                } catch (error) {
                    console.error('Error creating occupancy chart:', error);
                    errorMessage.value = 'Failed to create occupancy chart: ' + error.message;
                }
            } else {
                console.log('Occupancy chart not created - no data available');
            }
        };

        // Logout function
        const logout = async () => {
            try {
                const response = await fetch('/logout', {
                    method: 'POST',
                    credentials: 'include'
                });
                if (response.ok) {
                    window.location.href = '/';
                }
            } catch (error) {
                console.error('Logout error:', error);
                window.location.href = '/';
            }
        };

       
        onMounted(() => {
            console.log('Component mounted');
            
         
            const waitForChart = () => {
                if (typeof Chart !== 'undefined') {
                    console.log('Chart.js is available, loading data...');
                    loadSummaryData();
                } else {
                    console.log('Chart.js not ready, waiting...');
                    setTimeout(waitForChart, 200);
                }
            };
            
            // Start checking after a short delay
            setTimeout(waitForChart, 100);
        });

        return {
            loading,
            errorMessage,
            summaryData,
            metadata,
            hasRevenueData,
            hasOccupancyData,
            logout,
            loadSummaryData
        };
    }
}).mount('#admin-app');

// Global logout function for navbar button
function doLogout() {
    if (confirm('Are you sure you want to logout?')) {
        fetch('/logout', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        }).then(response => {
            if (response.ok) {
                window.location.href = '/';
            } else {
                throw new Error('Logout failed');
            }
        }).catch(error => {
            console.error('Logout error:', error);
            window.location.href = '/';
        });
    }
}
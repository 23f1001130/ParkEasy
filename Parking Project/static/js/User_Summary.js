const { createApp } = Vue;

createApp({
    data() {
        return {
            loading: true,
            errorMessage: '',
            chartData: {
                labels: [],
                bookings: [],
                spending: []
            },
            chart: null
        }
    },
    mounted() {
        this.loadChartData();
    },
    methods: {
        async loadChartData() {
            this.loading = true;
            try {
                const response = await axios.get('/api/user/daily-summary');
                
                
                if (response.data && response.data.success) {
                    this.chartData = response.data.data;
                    
                    
                    //  Vue to render the DOM
                    await this.$nextTick();
                    
                    // Add a small delay to ensure DOM is ready
                    setTimeout(() => {
                        this.createChart();
                    }, 100);
                } else {
                    console.error('API returned unsuccessful response:', response.data);
                    this.showError('Failed to load chart data');
                }
            } catch (error) {
                console.error('Error loading chart data:', error);
                if (error.response) {
                    console.error('Error response:', error.response.data);
                    this.showError(`Error: ${error.response.status} - ${error.response.data.error || 'Unknown error'}`);
                } else {
                    this.showError('Network error - please check your connection');
                }
            } finally {
                this.loading = false;
            }
        },

        createChart() {
            const canvas = document.getElementById('dailyChart');
            if (!canvas) {
                console.error('Canvas element not found - DOM may not be ready yet');
                // Try again after a short delay
                setTimeout(() => {
                    this.createChart();
                }, 200);
                return;
            }

          
            
            const ctx = canvas.getContext('2d');

            if (this.chart) {
                this.chart.destroy();
            }

            this.chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: this.chartData.labels,
                    datasets: [
                        {
                            label: 'Daily Bookings',
                            data: this.chartData.bookings,
                            borderColor: '#28a745',
                            backgroundColor: 'rgba(40, 167, 69, 0.1)',
                            tension: 0.4,
                            fill: true,
                            yAxisID: 'y'
                        },
                        {
                            label: 'Daily Spending (₹)',
                            data: this.chartData.spending,
                            borderColor: '#ffc107',
                            backgroundColor: 'rgba(255, 193, 7, 0.1)',
                            tension: 0.4,
                            fill: true,
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                            labels: {
                                usePointStyle: true,
                                padding: 20
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(0, 0, 0, 0.8)',
                            titleColor: '#fff',
                            bodyColor: '#fff',
                            borderColor: '#28a745',
                            borderWidth: 1,
                            callbacks: {
                                label: function (context) {
                                    let label = context.dataset.label || '';
                                    if (label) label += ': ';
                                    if (context.dataset.label.includes('Spending')) {
                                        label += '₹' + context.parsed.y.toFixed(2);
                                    } else {
                                        label += context.parsed.y;
                                    }
                                    return label;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            display: true,
                            title: {
                                display: true,
                                text: 'Date',
                                color: '#666',
                                font: {
                                    size: 14,
                                    weight: 'bold'
                                }
                            },
                            grid: {
                                color: 'rgba(0, 0, 0, 0.1)'
                            }
                        },
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Number of Bookings',
                                color: '#28a745',
                                font: {
                                    size: 14,
                                    weight: 'bold'
                                }
                            },
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(40, 167, 69, 0.1)'
                            },
                            ticks: {
                                stepSize: 1
                            }
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Amount Spent (₹)',
                                color: '#ffc107',
                                font: {
                                    size: 14,
                                    weight: 'bold'
                                }
                            },
                            beginAtZero: true,
                            grid: {
                                drawOnChartArea: false
                            },
                            ticks: {
                                callback: function (value) {
                                    return '₹' + value.toFixed(0);
                                }
                            }
                        }
                    }
                }
            });

        },

        showError(message) {
            this.errorMessage = message;
            const toast = new bootstrap.Toast(document.getElementById('errorToast'));
            toast.show();
        }
    },

    beforeUnmount() {
        if (this.chart) {
            this.chart.destroy();
        }
    }
}).mount('#summaryApp');
const { createApp } = Vue;

createApp({
  delimiters: ['[[', ']]'],
  data() {
    return {
      username: '',
      fullname: '',
      address: '',
      pincode: '',
      password: '',
      message: '',
      success: false,
      loading: false
    };
  },
  methods: {
    async register() {
      this.loading = true;
      this.message = '';

      console.log('Starting registration...');

      try {
        const requestData = {
          username: this.username,
          fullname: this.fullname,
          address: this.address,
          pincode: this.pincode,
          password: this.password
        };

        console.log('Sending registration data:', requestData);

        const response = await axios.post('/api/auth/register', requestData);

        console.log('Registration response:', response.data);
        console.log('Response status:', response.status);

        if (response.data.success) {
          this.success = true;
          this.message = response.data.message || 'Registration successful! Redirecting...';

          console.log('Registration successful, redirecting...');
          window.location.href = '/user/dashboard';
        }

      } catch (err) {
        console.error('Registration error details:', err);
        console.error('Error response:', err.response?.data);
        console.error('Error status:', err.response?.status);

        this.success = false;
        this.message = err.response?.data?.error || 'Registration failed. Please try again.';
      } finally {
        this.loading = false;
      }
    }
  }
}).mount('#app');

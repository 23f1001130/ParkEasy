const { createApp } = Vue;

createApp({
  delimiters: ['[[', ']]'],
  data() {
    return {
      username: '',
      password: '',
      message: '',
      success: false,
      loading: false
    };
  },
  methods: {
    async login() {
      this.loading = true;
      this.message = '';
      try {
        const response = await axios.post('/login', {
          username: this.username,
          password: this.password
        });

        this.success = true;
        this.message = response.data.message || 'Login successful!';

        // Redirect based on role
        if (response.data.is_admin) {
          window.location.href = '/admin/dashboard';
        } else {
          window.location.href = '/user/dashboard';
        }

      } catch (err) {
        this.success = false;
        this.message = err.response?.data?.error || 'Invalid credentials.';
      } finally {
        this.loading = false;
      }
    }
  }
}).mount('#app');

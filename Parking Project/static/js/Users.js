const app = Vue.createApp({
  delimiters: ['[[', ']]'],
  data() {
    return {
      users: [],
      searchTerm: '',
      selectedUser: null,
      currentPage: 1,
      itemsPerPage: 10,
      sortField: 'created_at',
      sortOrder: 'desc',
      todayRegistrations: 0,
      weekRegistrations: 0
    };
  },

  computed: {
    filteredUsers() {
      let filtered = this.users;

      if (this.searchTerm.trim()) {
        const query = this.searchTerm.toLowerCase();
        filtered = this.users.filter(user =>
          user.full_name?.toLowerCase().includes(query) ||
          user.username.toLowerCase().includes(query) ||
          user.pincode.toString().includes(query) ||
          user.address?.toLowerCase().includes(query)
        );
      }

      return filtered.sort((a, b) => {
        let aVal = a[this.sortField];
        let bVal = b[this.sortField];

        if (this.sortField === 'created_at') {
          aVal = new Date(aVal);
          bVal = new Date(bVal);
        }

        return this.sortOrder === 'asc' ? aVal > bVal ? 1 : -1 : aVal < bVal ? 1 : -1;
      });
    },

    totalPages() {
      return Math.ceil(this.filteredUsers.length / this.itemsPerPage);
    },

    paginatedUsers() {
      const start = (this.currentPage - 1) * this.itemsPerPage;
      return this.filteredUsers.slice(start, start + this.itemsPerPage);
    },

    visiblePages() {
      const pages = [];
      const start = Math.max(1, this.currentPage - 2);
      const end = Math.min(this.totalPages, this.currentPage + 2);
      for (let i = start; i <= end; i++) {
        pages.push(i);
      }
      return pages;
    }
  },

  methods: {
    fetchUsers() {
      fetch('/admin/users/list')
        .then(res => res.json())
        .then(data => {
          if (data.users && data.statistics) {
            this.users = data.users;
            this.todayRegistrations = data.statistics.today_registrations;
            this.weekRegistrations = data.statistics.week_registrations;
          } else {
            this.users = Array.isArray(data) ? data : [];
            this.calculateStats();
          }
        })
        .catch(err => {
          console.error('Error fetching users:', err);
          this.users = [
            {
              id: 1,
              username: 'john_doe',
              full_name: 'John Doe',
              pincode: '400001',
              address: '123 Main Street, Mumbai',
              created_at: '2024-01-15T10:30:00Z',
              email: 'john@example.com'
            },
            {
              id: 2,
              username: 'jane_smith',
              full_name: 'Jane Smith',
              pincode: '400002',
              address: '456 Park Avenue, Mumbai',
              created_at: '2024-01-16T14:20:00Z',
              email: 'jane@example.com'
            }
          ];
          this.calculateStats();
        });
    },

    calculateStats() {
      const today = new Date();
      const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

      this.todayRegistrations = this.users.filter(user =>
        new Date(user.created_at).toDateString() === today.toDateString()
      ).length;

      this.weekRegistrations = this.users.filter(user =>
        new Date(user.created_at) >= weekAgo
      ).length;
    },

    sortBy(field) {
      if (this.sortField === field) {
        this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        this.sortField = field;
        this.sortOrder = 'asc';
      }
      this.currentPage = 1;
    },

    changePage(page) {
      if (page >= 1 && page <= this.totalPages) {
        this.currentPage = page;
      }
    },

    viewUserDetails(user) {
      this.selectedUser = user;
      new bootstrap.Modal(document.getElementById('userDetailsModal')).show();
    },

    viewUserBookings(user) {
      alert(`View bookings for ${user.username} - Feature coming soon!`);
    },

    deactivateUser(userId) {
      if (!confirm("Are you sure you want to deactivate this user?")) return;

      fetch(`/admin/users/${userId}/deactivate`, { method: 'POST' })
        .then(res => {
          if (res.ok) {
            alert("User deactivated successfully");
            this.fetchUsers();
          } else {
            alert("Error deactivating user");
          }
        })
        .catch(err => {
          console.error('Error:', err);
          alert("Error deactivating user");
        });
    },

    exportUsers() {
      const csvContent = this.generateCSV();
      const blob = new Blob([csvContent], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `users_export_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    },

    generateCSV() {
      const headers = ['S.No.', 'Full Name', 'Username', 'Pincode', 'Address', 'Registered Date'];
      const rows = this.users.map((user, index) => [
        index + 1,
        user.full_name || 'N/A',
        user.username,
        user.pincode,
        user.address,
        this.formatDate(user.created_at)
      ]);
      return [headers, ...rows].map(row => row.map(field => `"${field}"`).join(',')).join('\n');
    },

    truncateAddress(address) {
      return address?.length > 50 ? address.substring(0, 50) + '...' : address || 'N/A';
    },

    formatDate(dateString) {
      return dateString ? new Date(dateString).toLocaleDateString() : 'N/A';
    },

    formatDateTime(dateString) {
      return dateString ? new Date(dateString).toLocaleString() : 'N/A';
    },

    logout() {
      fetch('/logout', { method: 'POST' })
        .then(response => {
          window.location.href = response.ok ? '/' : '/';
        })
        .catch(() => {
          window.location.href = '/';
        });
    }
  },

  mounted() {
    this.fetchUsers();
  }
});

app.mount('#users-app');

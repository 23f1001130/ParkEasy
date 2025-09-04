const app = Vue.createApp({
  delimiters: ['[[', ']]'],
  data() {
    return {
      lots: [],
      searchTerm: '',
      lotForm: {
        lot_name: '',
        address: '',
        pincode: '',
        price_per_hour: '',
        number_of_spots: ''
      },
      isEditMode: false,
      selectedSpot: {},
      totalSpots: 0,
      occupiedSpots: 0
    };
  },

  computed: {
    filteredLots() {
      if (!this.searchTerm.trim()) return this.lots;
      const query = this.searchTerm.toLowerCase();
      return this.lots.filter(lot =>
        lot.lot_name.toLowerCase().includes(query) ||
        lot.pincode.toString().includes(query)
      );
    }
  },

  methods: {
    fetchLots() {
      fetch('/admin/lots')
        .then(res => res.json())
        .then(async data => {
          this.lots = data;
          for (let lot of this.lots) {
            const res = await fetch(`/admin/spots/${lot.id}`);
            if (res.ok) {
              const spots = await res.json();
              lot.spots = spots.map(s => ({
                ...s,
                status: s.is_reserved ? 'O' : 'A'
              }));
              lot.total_spots = spots.length;
              lot.occupied_spots = spots.filter(s => s.status === 'O').length;
              lot.available_spots = spots.filter(s => s.status === 'A').length;
            } else {
              lot.spots = [];
              lot.total_spots = 0;
              lot.occupied_spots = 0;
              lot.available_spots = 0;
            }
          }
          this.calculateStats();
        });
    },

    calculateStats() {
      this.totalSpots = this.lots.reduce((sum, lot) => sum + (lot.total_spots || 0), 0);
      this.occupiedSpots = this.lots.reduce((sum, lot) => sum + (lot.occupied_spots || 0), 0);
    },

    openLotModal(edit, lot = null) {
      this.isEditMode = edit;
      this.lotForm = edit ? { ...lot } : {
        lot_name: '',
        address: '',
        pincode: '',
        price_per_hour: '',
        number_of_spots: ''
      };
      new bootstrap.Modal(document.getElementById('lotModal')).show();
    },

    saveLot() {
      const url = this.isEditMode ? `/admin/lots/${this.lotForm.id}` : '/admin/lots';
      const method = this.isEditMode ? 'PUT' : 'POST';
      const spots = parseInt(this.lotForm.number_of_spots);

      if (isNaN(spots) || spots < 1) {
        alert("Please enter a valid number of spots");
        return;
      }

      const payload = {
        lot_name: this.lotForm.lot_name,
        address: this.lotForm.address,
        pincode: this.lotForm.pincode,
        price_per_hour: parseFloat(this.lotForm.price_per_hour),
        number_of_spots: spots
      };

      fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(response => {
          if (!response.ok) throw new Error("Failed to save lot");
          return response.json();
        })
        .then(data => {
          alert("Lot saved successfully");
          bootstrap.Modal.getInstance(document.getElementById('lotModal')).hide();
          this.fetchLots();
          this.resetForm();
        })
        .catch(err => {
          console.error(err);
          alert("Error saving lot");
        });
    },

    resetForm() {
      this.lotForm = {
        lot_name: '',
        address: '',
        pincode: '',
        price_per_hour: '',
        number_of_spots: ''
      };
    },

    deleteLot(id) {
      if (!confirm("Are you sure you want to delete this parking lot?")) return;
      fetch(`/admin/lots/${id}`, { method: 'DELETE' })
        .then(res => {
          if (res.ok) {
            this.fetchLots();
          } else {
            alert("Cannot delete lot. Make sure all spots are empty.");
          }
        });
    },

    viewSpotDetails(spot) {
      this.selectedSpot = spot;
      new bootstrap.Modal(document.getElementById('spotModal')).show();
    },

    formatDateTime(ts) {
      if (!ts) return 'N/A';
      return new Date(ts).toLocaleString();
    },

    calculateDuration(ts) {
      if (!ts) return 'N/A';
      const start = new Date(ts);
      const now = new Date();
      const diff = Math.floor((now - start) / 60000);
      return diff < 60 ? `${diff} min` : `${Math.floor(diff / 60)}h ${diff % 60}m`;
    },

    logout() {
      fetch('/logout', { method: 'POST' })
        .then(response => {
          if (response.ok) {
            window.location.href = '/';
          } else {
            alert('Logout failed. Please try again.');
          }
        })
        .catch(error => {
          console.error('Logout error:', error);
          window.location.href = '/';
        });
    }
  },

  mounted() {
    this.fetchLots();
  }
});

app.mount('#admin-app');

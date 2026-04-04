Component({
  properties: {
    visible: { type: Boolean, value: false },
    logs: { type: Array, value: [] },
    matched: { type: Boolean, value: false },
  },

  data: {
    rainRows: [],
  },

  lifetimes: {
    attached() {
      const seed = '01A2A<>[]{}::#@$%&*';
      const rows = [];
      for (let i = 0; i < 28; i++) {
        let row = '';
        for (let j = 0; j < 36; j++) {
          row += seed[Math.floor(Math.random() * seed.length)];
        }
        rows.push(row);
      }
      this.setData({ rainRows: rows });
    },
  },
});

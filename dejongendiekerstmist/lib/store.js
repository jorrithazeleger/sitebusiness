import { readFileSync, writeFileSync, renameSync, mkdirSync, existsSync } from 'node:fs';
import path from 'node:path';

// Kleine JSON-opslag voor bestellingen en sleutels. Ruim voldoende voor duizenden kopers.
export class Store {
  constructor(dir) {
    this.file = path.join(dir, 'winkel.json');
    mkdirSync(dir, { recursive: true });
    this.data = { orders: {}, keys: {} };
    if (existsSync(this.file)) {
      this.data = JSON.parse(readFileSync(this.file, 'utf8'));
      this.data.orders ||= {};
      this.data.keys ||= {};
    }
  }

  save() {
    const tmp = this.file + '.tmp';
    writeFileSync(tmp, JSON.stringify(this.data, null, 2));
    renameSync(tmp, this.file);
  }

  getOrder(id) { return Object.hasOwn(this.data.orders, id) ? this.data.orders[id] : null; }

  putOrder(order) {
    this.data.orders[order.id] = order;
    this.save();
    return order;
  }

  findOrderByPayment(paymentId) {
    return Object.values(this.data.orders).find((o) => o.paymentId === paymentId) || null;
  }

  getKey(code) { return Object.hasOwn(this.data.keys, code) ? this.data.keys[code] : null; }

  putKey(code, info) {
    this.data.keys[code] = { ...info, createdAt: new Date().toISOString() };
    this.save();
  }
}

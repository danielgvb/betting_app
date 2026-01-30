import heapq
import datetime
import io
import csv
from flask import Flask, render_template, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# --- CONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cepeda_market.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MARKET DETAILS ---
MARKET_CONFIG = {
    "title": "Will Ivan Cepeda be elected President of Colombia?",
    "asset_name": "Ivan Cepeda (YES)",
    "description": "This market tracks the probability of Ivan Cepeda winning the next presidential election. Trading closes on Election Day.",
    "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Iv%C3%A1n_Cepeda_Castro%2C_Senator_of_Colombia.jpg/220px-Iv%C3%A1n_Cepeda_Castro%2C_Senator_of_Colombia.jpg" # Public domain image link
}

# --- DATABASE MODELS ---
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), nullable=False)
    side = db.Column(db.String(4), nullable=False) # 'buy' or 'sell'
    price = db.Column(db.Integer, nullable=False)  # Price in Cents (Probability)
    quantity = db.Column(db.Integer, nullable=False)
    remaining = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_email = db.Column(db.String(120), nullable=False)
    seller_email = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# --- THE MATCHING ENGINE ---
class OrderBook:
    def __init__(self):
        self.bids = [] 
        self.asks = [] 

    def reload_from_db(self):
        self.bids = []
        self.asks = []
        active_orders = Order.query.filter(Order.remaining > 0).all()
        for o in active_orders:
            if o.side == 'buy':
                heapq.heappush(self.bids, (-o.price, o.timestamp.timestamp(), o.id, o))
            else:
                heapq.heappush(self.asks, (o.price, o.timestamp.timestamp(), o.id, o))

    def process_order(self, email, side, price, qty):
        # 1. Save Order
        new_order = Order(user_email=email, side=side, price=price, quantity=qty, remaining=qty)
        db.session.add(new_order)
        db.session.commit()

        remaining_qty = qty
        
        # 2. Match
        if side == 'buy':
            while self.asks and self.asks[0][0] <= price and remaining_qty > 0:
                best_ask_price, _, ask_id, ask_order = self.asks[0]
                if ask_order.remaining <= 0:
                    heapq.heappop(self.asks)
                    continue

                trade_qty = min(remaining_qty, ask_order.remaining)
                self.record_trade(new_order, ask_order, best_ask_price, trade_qty)
                remaining_qty -= trade_qty
                
                if ask_order.remaining == 0: heapq.heappop(self.asks)

            if remaining_qty > 0:
                heapq.heappush(self.bids, (-price, new_order.timestamp.timestamp(), new_order.id, new_order))

        else: # Sell
            while self.bids and -self.bids[0][0] >= price and remaining_qty > 0:
                best_bid_price, _, bid_id, bid_order = self.bids[0]
                buy_price = -best_bid_price
                
                if bid_order.remaining <= 0:
                    heapq.heappop(self.bids)
                    continue

                trade_qty = min(remaining_qty, bid_order.remaining)
                self.record_trade(bid_order, new_order, buy_price, trade_qty)
                remaining_qty -= trade_qty
                
                if bid_order.remaining == 0: heapq.heappop(self.bids)

            if remaining_qty > 0:
                heapq.heappush(self.asks, (price, new_order.timestamp.timestamp(), new_order.id, new_order))
        
        return True

    def record_trade(self, buyer_order, seller_order, price, qty):
        trade = Trade(
            buyer_email=buyer_order.user_email,
            seller_email=seller_order.user_email,
            price=price,
            quantity=qty
        )
        db.session.add(trade)
        buyer_order.remaining -= qty
        seller_order.remaining -= qty
        db.session.commit()

market = OrderBook()
with app.app_context():
    db.create_all()
    market.reload_from_db()

# --- ROUTES ---

@app.route('/')
def index():
    # Pass market details to the frontend
    return render_template('index.html', market=MARKET_CONFIG)

@app.route('/api/book')
def get_book():
    def get_levels(heap_list, is_buy):
        levels = {}
        for item in heap_list:
            order = item[3]
            price = order.price
            if price not in levels: levels[price] = 0
            levels[price] += order.remaining
        return [{'price': p, 'qty': q} for p, q in sorted(levels.items(), reverse=is_buy)]

    return jsonify({
        'bids': get_levels(market.bids, True),
        'asks': get_levels(market.asks, False),
        'last_trade': get_last_trade_price()
    })

def get_last_trade_price():
    last = Trade.query.order_by(Trade.timestamp.desc()).first()
    return last.price if last else None

@app.route('/api/order', methods=['POST'])
def place_order():
    data = request.json
    market.process_order(data['email'], data['side'], int(data['price']), int(data['qty']))
    return jsonify({'status': 'ok'})

@app.route('/download_report')
def download_report():
    trades = Trade.query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Winner (Buyer)', 'Loser (Seller)', 'Odds (%)', 'Contracts', 'Risk ($)', 'Time'])
    for t in trades:
        total = (t.price * t.quantity) / 100
        writer.writerow([t.id, t.buyer_email, t.seller_email, t.price, t.quantity, total, t.timestamp])
    output.seek(0)
    return make_response(output.getvalue(), 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename=cepeda_market_trades.csv'
    })

if __name__ == '__main__':
    app.run(debug=True)
from flask import Flask, render_template, request, jsonify
import heapq

app = Flask(__name__)

# --- THE LOGIC ENGINE (ORDER BOOK) ---
class OrderBook:
    def __init__(self):
        self.bids = []  # Buy orders (Max-Heap using negative numbers)
        self.asks = []  # Sell orders (Min-Heap)
        self.trade_history = []

    def add_order(self, side, price, qty):
        # 1. Try to Match
        remaining_qty = qty
        
        if side == 'buy':
            # Match against Asks (Sellers)
            while self.asks and self.asks[0]['price'] <= price and remaining_qty > 0:
                best_ask = self.asks[0]
                trade_qty = min(remaining_qty, best_ask['qty'])
                
                # Execute Trade
                self.trade_history.append({
                    'price': best_ask['price'],
                    'qty': trade_qty,
                    'side': 'buy_match'
                })
                
                remaining_qty -= trade_qty
                best_ask['qty'] -= trade_qty
                
                if best_ask['qty'] == 0:
                    heapq.heappop(self.asks)

            # Add remaining to Book
            if remaining_qty > 0:
                # Store negative price for Max-Heap behavior
                heapq.heappush(self.bids, {'price': -price, 'qty': remaining_qty})

        else: # side == 'sell'
            # Match against Bids (Buyers)
            while self.bids and -self.bids[0]['price'] >= price and remaining_qty > 0:
                best_bid = self.bids[0]
                buy_price = -best_bid['price']
                trade_qty = min(remaining_qty, best_bid['qty'])
                
                # Execute Trade
                self.trade_history.append({
                    'price': buy_price,
                    'qty': trade_qty,
                    'side': 'sell_match'
                })
                
                remaining_qty -= trade_qty
                best_bid['qty'] -= trade_qty
                
                if best_bid['qty'] == 0:
                    heapq.heappop(self.bids)

            # Add remaining to Book
            if remaining_qty > 0:
                heapq.heappush(self.asks, {'price': price, 'qty': remaining_qty})
        
        return remaining_qty

# Initialize Market
market = OrderBook()

# --- THE WEB ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/book')
def get_book():
    # Format data for frontend
    # Convert bids back to positive numbers for display
    formatted_bids = [{'price': -b['price'], 'qty': b['qty']} for b in sorted(market.bids, key=lambda x: x['price'])]
    formatted_asks = [{'price': a['price'], 'qty': a['qty']} for a in sorted(market.asks, key=lambda x: x['price'])]
    
    return jsonify({
        'bids': formatted_bids, 
        'asks': formatted_asks,
        'trades': market.trade_history[-10:] # Last 10 trades
    })

@app.route('/api/order', methods=['POST'])
def place_order():
    data = request.json
    market.add_order(data['side'], int(data['price']), int(data['qty']))
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)
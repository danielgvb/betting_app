import math
import datetime
import io
import csv
from flask import Flask, render_template, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# --- DATABASE CONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///market.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- DATABASE MODEL ---
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), nullable=False)
    outcome = db.Column(db.String(10), nullable=False) # 'YES' or 'NO'
    quantity = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)         # How much they paid
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'email': self.user_email,
            'outcome': self.outcome,
            'qty': self.quantity,
            'cost': self.cost,
            'time': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

# --- THE AMM ENGINE (The "House" Algo) ---
class MarketMaker:
    def __init__(self, liquidity_param=100.0):
        self.b = liquidity_param
        # We will load the state from the DB ideally, but for MVP we reset or simple sum
        # For a persistent market, you'd calculate these from the Trade table on startup.
        self.q_yes = 0.0
        self.q_no = 0.0

    def reload_state(self):
        """Recalculates market state from the database history"""
        with app.app_context():
            trades = Trade.query.all()
            self.q_yes = sum(t.quantity for t in trades if t.outcome == 'YES')
            self.q_no = sum(t.quantity for t in trades if t.outcome == 'NO')

    def cost_function(self, q_yes, q_no):
        exp_yes = math.exp(q_yes / self.b)
        exp_no = math.exp(q_no / self.b)
        return self.b * math.log(exp_yes + exp_no)

    def get_price(self, outcome):
        exp_yes = math.exp(self.q_yes / self.b)
        exp_no = math.exp(self.q_no / self.b)
        denominator = exp_yes + exp_no
        return exp_yes / denominator if outcome == 'YES' else exp_no / denominator

    def trade(self, outcome, quantity):
        old_cost = self.cost_function(self.q_yes, self.q_no)
        new_q_yes = self.q_yes + (quantity if outcome == 'YES' else 0)
        new_q_no = self.q_no + (quantity if outcome == 'NO' else 0)
        new_cost = self.cost_function(new_q_yes, new_q_no)
        
        trade_cost = new_cost - old_cost
        self.q_yes = new_q_yes
        self.q_no = new_q_no
        return trade_cost

market = MarketMaker(liquidity_param=100)

# Create Database and Reload State on Startup
with app.app_context():
    db.create_all()
    market.reload_state()

# --- ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/state')
def get_state():
    return jsonify({
        'price_yes': market.get_price('YES'),
        'price_no': market.get_price('NO'),
        'shares_yes': market.q_yes,
        'shares_no': market.q_no
    })

@app.route('/api/buy', methods=['POST'])
def buy():
    data = request.json
    email = data.get('email')
    outcome = data['outcome']
    qty = float(data['qty'])
    
    if not email:
        return jsonify({'error': 'Email is required'}), 400

    # 1. Calculate Cost via AMM
    cost = market.trade(outcome, qty)
    
    # 2. Save to Database
    new_trade = Trade(user_email=email, outcome=outcome, quantity=qty, cost=cost)
    db.session.add(new_trade)
    db.session.commit()
    
    return jsonify({
        'cost': cost,
        'new_price_yes': market.get_price('YES'),
        'new_price_no': market.get_price('NO')
    })

@app.route('/download_trades')
def download_trades():
    """Export all trades to CSV for Excel"""
    trades = Trade.query.all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['Trade ID', 'User Email', 'Outcome Bought', 'Shares', 'Price Paid ($)', 'Timestamp'])
    
    # Data
    for t in trades:
        writer.writerow([t.id, t.user_email, t.outcome, t.quantity, round(t.cost, 2), t.timestamp])
    
    output.seek(0)
    
    return make_response(output.getvalue(), 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename=market_trades.csv'
    })

if __name__ == '__main__':
    app.run(debug=True)
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import os
import razorpay
import hmac
import hashlib
import gspread
from google.oauth2.service_account import Credentials
import json

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'goa12L')

# Razorpay client
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# Try loading from env first
creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

if creds_json:
    # Running on Render (env var set)
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
else:
    # Running locally (load from file)
    creds = Credentials.from_service_account_file("service_account.json", scopes=scope)

client = gspread.authorize(creds)
sheet = client.open(os.getenv("GOOGLE_SHEET_NAME", "AlsiumPayments")).sheet1


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/payment')
def payment():
    return render_template('payment.html', razorpay_key_id=RAZORPAY_KEY_ID)

@app.route('/int_sheet')
def int_sheet():
    return render_template('int_sheet_goa.html')



@app.route('/create_order', methods=['POST'])
def create_order():
    data = request.get_json()
    amount = data.get('amount', 1200)  # Default ₹12 (1200 paise)

    order_data = {
        'amount': amount,
        'currency': 'INR',
        'receipt': f'order_rcptid_{data.get("user_id", "guest")}'
    }

    try:
        order = razorpay_client.order.create(data=order_data)
        return jsonify({
            'order_id': order['id'],
            'amount': order['amount'],
            'currency': order['currency'],
            'key': RAZORPAY_KEY_ID
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/verify_payment', methods=['POST'])
def verify_payment():
    data = request.get_json()
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature = data.get('razorpay_signature')
    user_data = data.get('user_data')

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature, user_data]):
        return jsonify({'error': 'Missing required payment or user data'}), 400

    try:
        # Verify Razorpay signature
        generated_signature = hmac.new(
            key=RAZORPAY_KEY_SECRET.encode('utf-8'),
            msg=f"{razorpay_order_id}|{razorpay_payment_id}".encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        if generated_signature != razorpay_signature:
            return jsonify({'error': 'Invalid payment signature'}), 400

        # Extract user details
        ig_username = user_data.get('ig_username')
        full_name = user_data.get('full_name')
        email = user_data.get('email')
        phone = user_data.get('phone')
        state = user_data.get('state')

        if not all([ig_username, full_name, email, phone, state]):
            return jsonify({'error': 'All user fields are required'}), 400

        # Append row to Google Sheet
        sheet.append_row([
            ig_username,
            full_name,
            email,
            phone,
            state,
            razorpay_order_id,
            razorpay_payment_id,
            "success"
        ])

        return jsonify({
            'status': 'Payment verified and user saved to Google Sheet',
            'user': ig_username
        }), 200

    except Exception as e:
        return jsonify({'error': f'Failed to verify payment or save user: {str(e)}'}), 400


if __name__ == '__main__':
    app.run(debug=True)

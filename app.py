from flask import Flask, request, jsonify
from crunchyroll_checker import CrunchyrollChecker
import logging
import os
from threading import Lock
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
checker_lock = Lock()

# Rate limiting storage (in-memory for simplicity)
request_times = {}

def is_rate_limited(ip, max_requests=10, window_seconds=60):
    """Simple rate limiting"""
    current_time = time.time()
    if ip not in request_times:
        request_times[ip] = []
    
    # Remove old requests
    request_times[ip] = [t for t in request_times[ip] if current_time - t < window_seconds]
    
    # Check if over limit
    if len(request_times[ip]) >= max_requests:
        return True
    
    # Add current request
    request_times[ip].append(current_time)
    return False

@app.route('/')
def home():
    return jsonify({
        'status': 'active',
        'service': 'Crunchyroll Account Checker API',
        'version': '1.0.0',
        'endpoints': {
            '/api/check': 'POST - Check single account',
            '/api/batch-check': 'POST - Check multiple accounts (max 5)',
            '/api/health': 'GET - Health check'
        },
        'usage': {
            'single_check': 'Send POST with {"email": "email", "password": "password"}',
            'batch_check': 'Send POST with {"accounts": ["email:pass", "email:pass"]}'
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'service': 'Crunchyroll Checker API'
    })

@app.route('/api/check', methods=['POST'])
def check_account():
    """
    Check a single Crunchyroll account
    """
    client_ip = request.remote_addr
    
    # Rate limiting
    if is_rate_limited(client_ip):
        return jsonify({
            'success': False,
            'formatted_response': '❌ Rate Limited\n\nPlease wait 60 seconds before making another request.',
            'error': 'Rate limit exceeded'
        }), 429
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'formatted_response': '❌ Invalid Request\n\nError: No JSON data provided',
                'error': 'No data provided'
            }), 400
        
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        
        if not email or not password:
            return jsonify({
                'success': False,
                'formatted_response': '❌ Invalid Request\n\nError: Email and password are required',
                'error': 'Missing credentials'
            }), 400
        
        # Validate email format
        if '@' not in email or '.' not in email:
            return jsonify({
                'success': False,
                'formatted_response': f'❌ Invalid Email\n\nAccount: {email}\nError: Invalid email format',
                'error': 'Invalid email format'
            }), 400
        
        logger.info(f"Checking account: {email}")
        
        with checker_lock:
            checker = CrunchyrollChecker()
            try:
                result = checker.check_single_account(email, password)
                return jsonify(result)
            finally:
                checker.close()
                
    except Exception as e:
        logger.error(f"Error checking account: {str(e)}")
        return jsonify({
            'success': False,
            'formatted_response': f'❌ Server Error\n\nError: Internal server error',
            'error': str(e)
        }), 500

@app.route('/api/batch-check', methods=['POST'])
def batch_check():
    """
    Check multiple accounts (max 5)
    """
    client_ip = request.remote_addr
    
    # Stricter rate limiting for batch requests
    if is_rate_limited(client_ip, max_requests=3, window_seconds=120):
        return jsonify({
            'success': False,
            'formatted_response': '❌ Rate Limited\n\nPlease wait 2 minutes before making another batch request.',
            'error': 'Rate limit exceeded'
        }), 429
    
    try:
        data = request.get_json()
        
        if not data or 'accounts' not in data:
            return jsonify({
                'success': False,
                'formatted_response': '❌ Invalid Request\n\nError: No accounts data provided',
                'error': 'No accounts provided'
            }), 400
        
        accounts = data['accounts']
        
        if not isinstance(accounts, list):
            return jsonify({
                'success': False,
                'formatted_response': '❌ Invalid Request\n\nError: Accounts must be a list',
                'error': 'Invalid accounts format'
            }), 400
        
        if len(accounts) > 5:
            return jsonify({
                'success': False,
                'formatted_response': '❌ Too Many Accounts\n\nError: Maximum 5 accounts allowed per batch',
                'error': 'Too many accounts'
            }), 400
        
        results = []
        checker = CrunchyrollChecker()
        
        try:
            for i, account_str in enumerate(accounts):
                if not isinstance(account_str, str) or ':' not in account_str:
                    results.append(f"❌ Invalid Format\n\nLine {i+1}: {account_str}\nError: Use email:password format")
                    continue
                
                email, password = account_str.split(':', 1)
                email = email.strip()
                password = password.strip()
                
                # Validate email
                if '@' not in email or '.' not in email:
                    results.append(f"❌ Invalid Email\n\nAccount: {email}\nError: Invalid email format")
                    continue
                
                logger.info(f"Batch checking {i+1}/{len(accounts)}: {email}")
                
                # Add delay between requests
                if i > 0:
                    time.sleep(3)
                
                result = checker.check_single_account(email, password)
                results.append(result['formatted_response'])
                
            return jsonify({
                'success': True,
                'results': results,
                'total_checked': len(results),
                'formatted_response': '\n\n'.join(results)
            })
            
        finally:
            checker.close()
            
    except Exception as e:
        logger.error(f"Error in batch check: {str(e)}")
        return jsonify({
            'success': False,
            'formatted_response': f'❌ Server Error\n\nError: Internal server error',
            'error': str(e)
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'message': 'Check / for available endpoints'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
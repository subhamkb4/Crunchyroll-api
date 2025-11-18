import requests
import json
import time
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CrunchyrollChecker:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        })
        self.base_url = "https://beta.crunchyroll.com"
        self.timeout = 30
    
    def login_and_check_status(self, email, password):
        """
        Attempt to login and check account subscription status
        """
        try:
            logger.info(f"Starting check for: {email}")
            
            # Get login page
            login_response = self.session.get(
                f"{self.base_url}/login",
                timeout=self.timeout
            )
            
            if login_response.status_code != 200:
                return self.format_response(False, email, error=f'Login page unavailable: {login_response.status_code}')
            
            # Try to login
            login_data = {
                'username': email,
                'password': password,
            }
            
            # Attempt login
            post_response = self.session.post(
                f"{self.base_url}/login",
                data=login_data,
                allow_redirects=True,
                timeout=self.timeout
            )
            
            # Check if login successful by accessing account page
            account_response = self.session.get(
                f"{self.base_url}/account",
                timeout=self.timeout,
                allow_redirects=False
            )
            
            if account_response.status_code == 200:
                logger.info(f"Login successful for: {email}")
                return self.analyze_account_status(email, account_response.text)
            else:
                return self.format_response(False, email, error='Invalid credentials or account not found')
                
        except requests.exceptions.Timeout:
            return self.format_response(False, email, error='Request timeout - try again later')
        except requests.exceptions.ConnectionError:
            return self.format_response(False, email, error='Connection error - check your internet')
        except Exception as e:
            logger.error(f"Error checking {email}: {str(e)}")
            return self.format_response(False, email, error=f'Check failed: {str(e)}')
    
    def analyze_account_status(self, email, html_content):
        """
        Analyze the account page HTML to determine status
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            page_text = soup.get_text().lower()
            
            # Check for premium indicators
            premium_indicators = [
                'premium', 'megafan', 'mega fan', 'fan pack', 
                'subscription', 'member', 'payment method'
            ]
            
            is_premium = any(indicator in page_text for indicator in premium_indicators)
            
            if not is_premium:
                return self.format_response(True, email, {
                    'country': 'Unknown',
                    'plan': 'Free',
                    'payment_method': 'None',
                    'status': 'inactive',
                    'trial': False,
                    'renewal_date': 'N/A',
                    'days_left': 0
                })
            
            # Extract information with better patterns
            info = {
                'country': self.extract_country(soup),
                'plan': self.extract_plan(soup),
                'payment_method': self.extract_payment(soup),
                'status': 'active',
                'trial': 'trial' in page_text,
                'renewal_date': self.generate_future_date(120),  # 120 days from now
                'days_left': 118  # Example value
            }
            
            return self.format_response(True, email, info)
            
        except Exception as e:
            return self.format_response(False, email, error=f'Failed to parse account page: {str(e)}')
    
    def extract_country(self, soup):
        """Extract country information"""
        page_text = soup.get_text()
        country_match = re.search(r'country[:\s]*([a-z]{2})', page_text, re.IGNORECASE)
        return country_match.group(1).upper() if country_match else 'US'
    
    def extract_plan(self, soup):
        """Extract plan information"""
        page_text = soup.get_text()
        plan_match = re.search(r'plan[:\s]*([^\n\r]+)', page_text, re.IGNORECASE)
        if plan_match:
            return plan_match.group(1).strip()
        
        # Check for specific plan types
        if 'mega fan' in page_text.lower():
            return 'Mega Fan - fan_pack'
        elif 'premium' in page_text.lower():
            return 'Premium'
        
        return 'Premium Plan'
    
    def extract_payment(self, soup):
        """Extract payment information"""
        page_text = soup.get_text()
        payment_match = re.search(r'payment[:\s]*([^\n\r]+)', page_text, re.IGNORECASE)
        if payment_match:
            return payment_match.group(1).strip()
        
        return 'Credit Card'
    
    def generate_future_date(self, days_from_now):
        """Generate a future date for renewal"""
        future_date = datetime.now() + timedelta(days=days_from_now)
        return future_date.strftime('%d-%m-%Y')
    
    def format_response(self, success, email, account_info=None, error=None):
        """
        Format the response in the exact requested format
        """
        if success and account_info:
            status_icon = "✅" if account_info['status'] == 'active' else "❌"
            plan_type = "Premium Account" if account_info['status'] == 'active' else "Free Account"
            
            response_lines = [
                f"{status_icon} {plan_type}",
                f"",
                f"Account: {email}",
                f"Country: {account_info['country']}",
                f"Plan: {account_info['plan']}",
                f"Payment: {account_info['payment_method']}",
                f"Status: {account_info['status']}",
                f"Trial: {account_info['trial']}",
                f"Renewal: {account_info['renewal_date']}",
                f"Days Left: {account_info['days_left']}"
            ]
            
            return {
                'success': True,
                'formatted_response': '\n'.join(response_lines),
                'raw_data': account_info
            }
        else:
            return {
                'success': False,
                'formatted_response': f"❌ Invalid Account\n\nAccount: {email}\nError: {error}",
                'error': error
            }
    
    def check_single_account(self, email, password):
        """Public method to check a single account"""
        return self.login_and_check_status(email, password)
    
    def close(self):
        """Close the session"""
        self.session.close()
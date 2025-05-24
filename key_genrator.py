#!/usr/bin/env python3
"""
Key Generator Admin Panel
Generate access keys for Telegram bot users
"""

import os
import secrets
import string
import psycopg2
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(16))

# Database setup
DATABASE_URL = os.environ.get('DATABASE_URL')

def init_database():
    """Initialize the database with required tables"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Create access_keys table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS access_keys (
            id SERIAL PRIMARY KEY,
            access_key VARCHAR(50) UNIQUE NOT NULL,
            expiry_date TIMESTAMP NOT NULL,
            is_unlimited BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used_count INTEGER DEFAULT 0,
            last_used TIMESTAMP,
            status VARCHAR(20) DEFAULT 'active'
        )
        """)
        
        conn.commit()
        conn.close()
        print("✅ Database initialized successfully")
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

def generate_access_key():
    """Generate a random access key"""
    length = 12
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

@app.route('/')
def index():
    """Admin dashboard"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Get all keys
        cursor.execute("""
        SELECT access_key, expiry_date, is_unlimited, created_at, used_count, 
               last_used, status
        FROM access_keys 
        ORDER BY created_at DESC
        """)
        keys = cursor.fetchall()
        
        # Get statistics
        cursor.execute("SELECT COUNT(*) FROM access_keys WHERE status = 'active'")
        active_keys = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM access_keys WHERE expiry_date > NOW() AND status = 'active'")
        valid_keys = cursor.fetchone()[0]
        
        conn.close()
        
        return render_template('dashboard.html', keys=keys, active_keys=active_keys, valid_keys=valid_keys)
        
    except Exception as e:
        flash(f"Error loading dashboard: {e}", 'error')
        return render_template('dashboard.html', keys=[], active_keys=0, valid_keys=0)

@app.route('/generate_key', methods=['POST'])
def generate_key():
    """Generate a new access key"""
    try:
        duration_type = request.form.get('duration_type')
        custom_days = request.form.get('custom_days', type=int)
        
        # Generate unique key
        while True:
            new_key = generate_access_key()
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM access_keys WHERE access_key = %s", (new_key,))
            if not cursor.fetchone():
                break
            conn.close()
        
        # Calculate expiry date
        if duration_type == 'unlimited':
            expiry_date = datetime(2099, 12, 31)
            is_unlimited = True
        elif duration_type == '1_day':
            expiry_date = datetime.now() + timedelta(days=1)
            is_unlimited = False
        elif duration_type == '7_days':
            expiry_date = datetime.now() + timedelta(days=7)
            is_unlimited = False
        elif duration_type == '30_days':
            expiry_date = datetime.now() + timedelta(days=30)
            is_unlimited = False
        elif duration_type == '365_days':
            expiry_date = datetime.now() + timedelta(days=365)
            is_unlimited = False
        elif duration_type == 'custom' and custom_days:
            expiry_date = datetime.now() + timedelta(days=custom_days)
            is_unlimited = False
        else:
            flash("Invalid duration selected", 'error')
            return redirect(url_for('index'))
        
        # Insert key into database
        cursor.execute("""
        INSERT INTO access_keys (access_key, expiry_date, is_unlimited)
        VALUES (%s, %s, %s)
        """, (new_key, expiry_date, is_unlimited))
        
        conn.commit()
        conn.close()
        
        flash(f"✅ Key generated successfully: {new_key}", 'success')
        
    except Exception as e:
        flash(f"Error generating key: {e}", 'error')
    
    return redirect(url_for('index'))

@app.route('/delete_key/<key_id>')
def delete_key(key_id):
    """Delete/deactivate a key"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE access_keys SET status = 'deleted' WHERE id = %s", (key_id,))
        conn.commit()
        conn.close()
        
        flash("Key deactivated successfully", 'success')
        
    except Exception as e:
        flash(f"Error deleting key: {e}", 'error')
    
    return redirect(url_for('index'))

@app.route('/api/check_key', methods=['POST'])
def check_key_api():
    """API endpoint to check if a key is valid"""
    try:
        data = request.get_json()
        access_key = data.get('access_key', '').strip().upper()
        
        if not access_key:
            return jsonify({'valid': False, 'message': 'No key provided'})
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check key validity
        cursor.execute("""
        SELECT expiry_date, is_unlimited, status
        FROM access_keys 
        WHERE access_key = %s
        """, (access_key,))
        
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({'valid': False, 'message': 'Invalid key'})
        
        expiry_date, is_unlimited, status = result
        
        if status != 'active':
            conn.close()
            return jsonify({'valid': False, 'message': 'Key has been deactivated'})
        
        # Check if key is expired
        if not is_unlimited and expiry_date < datetime.now():
            conn.close()
            return jsonify({'valid': False, 'message': 'Key has expired'})
        
        # Update usage statistics
        cursor.execute("""
        UPDATE access_keys 
        SET used_count = used_count + 1, last_used = CURRENT_TIMESTAMP
        WHERE access_key = %s
        """, (access_key,))
        
        conn.commit()
        conn.close()
        
        expiry_str = "Unlimited" if is_unlimited else expiry_date.strftime("%Y-%m-%d")
        
        return jsonify({
            'valid': True, 
            'message': f'Access granted until {expiry_str}',
            'expiry': expiry_str
        })
        
    except Exception as e:
        return jsonify({'valid': False, 'message': f'Server error: {str(e)}'})

if __name__ == '__main__':
    init_database()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

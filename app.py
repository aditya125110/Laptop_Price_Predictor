import os
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timezone
import pytz
import pickle
import numpy as np
import pandas as pd
import sqlite3
import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with your actual secret key

# Load model and data
pipe = pickle.load(open('model/pipe.pkl', 'rb'))
df = pickle.load(open('model/df.pkl', 'rb'))


# Database setup
def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn



@app.route('/')
def prediction():
    if 'username' in session:
        return render_template('prediction.html', 
                               companies=df['Company'].unique(),
                               types=df['TypeName'].unique(),
                               cpus=df['Cpu brand'].unique(),
                               gpus=df['Gpu brand'].unique(),
                               os_options=df['os'].unique())
    return redirect(url_for('login'))

@app.route('/predict', methods=['POST'])
def predict():
    company = request.form.get('company')
    type = request.form.get('type')
    ram = int(request.form.get('ram'))
    weight = float(request.form.get('weight'))
    touchscreen = 1 if request.form.get('touchscreen') == 'Yes' else 0
    ips = 1 if request.form.get('ips') == 'Yes' else 0
    screen_size = float(request.form.get('screen_size'))
    resolution = request.form.get('resolution')
    X_res, Y_res = map(int, resolution.split('x'))
    ppi = ((X_res ** 2) + (Y_res ** 2)) ** 0.5 / screen_size
    cpu = request.form.get('cpu')
    hdd = int(request.form.get('hdd'))
    ssd = int(request.form.get('ssd'))
    gpu = request.form.get('gpu')
    os = request.form.get('os')

    # Create query as a DataFrame with the correct column names
    query = pd.DataFrame([[company, type, ram, weight, touchscreen, ips, ppi, cpu, hdd, ssd, gpu, os]], 
                         columns=['Company', 'TypeName', 'Ram', 'Weight', 'Touchscreen', 'Ips', 'ppi', 
                                  'Cpu brand', 'HDD', 'SSD', 'Gpu brand', 'os'])
    
    # Perform prediction
    price = int(np.exp(pipe.predict(query)[0]))

    return render_template('result.html', price=price)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        registration_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                         (username, password))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return 'Username already exists'
        conn.close()
        
        return redirect(url_for('login'))
    
    return render_template('signup.html')
print("Current UTC Time:", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and user['password'] == password:
            session['username'] = username
            return redirect(url_for('prediction'))
        else:
            error = 'Invalid username or password'
    
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')    

def load_admin_credentials():
    with open('static/admin_credentials.csv', mode='r') as file:
        reader = csv.DictReader(file)
        return {row['username']: row for row in reader}

admin_credentials = load_admin_credentials()

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username in admin_credentials and admin_credentials[username]['password'] == password:
            session['admin_name'] = admin_credentials[username]['name']
            return redirect(url_for('welcome_admin'))
        else:
            error = 'Invalid username or password'
    
    return render_template('admin_login.html', error=error)

@app.route('/welcome_admin')
def welcome_admin():
    if 'admin_name' not in session:
        return redirect(url_for('admin_login'))
    
    # Fetch all users from the database
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    
    # Fetch all contact submissions from the database
    contact_submissions = conn.execute('SELECT * FROM contact_submissions').fetchall()
    conn.close()
    
    return render_template('welcome_admin.html', name=session['admin_name'], users=users, contact_submissions=contact_submissions)

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_name', None)
    return redirect(url_for('admin_login'))


@app.route('/view_users')
def view_users():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()

    # Convert registration_time from UTC to IST
    ist_tz = pytz.timezone('Asia/Kolkata')  # Indian Standard Time
    user_list = []  # Create a new list to hold user data

    for user in users:
        # Convert the registration_time to a datetime object
        utc_time = datetime.strptime(user['registration_time'], '%Y-%m-%d %H:%M:%S')
        utc_time = utc_time.replace(tzinfo=pytz.utc)  # Set timezone to UTC
        ist_time = utc_time.astimezone(ist_tz)  # Convert to IST
        
        # Create a new dictionary for the user with the converted time
        user_data = {
            'id': user['id'],
            'username': user['username'],
            'registration_time': ist_time.strftime('%Y-%m-%d %H:%M:%S')  # Format for display
        }
        user_list.append(user_data)  # Add the new user data to the list

    return render_template('view_users.html', users=user_list)

@app.route('/contact_me', methods=['POST'])
def contact_me():
    name = request.form['name']
    country_code = request.form['country_code']
    contact_number = request.form['contact_number']
    email = request.form['email']
    message = request.form['message']

    # Save the contact form submission to the database
    conn = get_db_connection()
    conn.execute('INSERT INTO contact_submissions (name, country_code, contact_number, email, message) VALUES (?, ?, ?, ?, ?)', 
                 (name, country_code, contact_number, email, message))
    conn.commit()
    conn.close()

    # Prepare the email content
    subject = "Contact Form Submission"
    body = f"""
    Name: {name}
    Contact Number: {country_code} {contact_number}
    Email: {email}
    Message: {message}
    """

    # Send the email
    send_email(subject, body)

    return render_template('thank_you.html')  # Create a thank you page or redirect to index

def send_email(subject, body):
    sender_email = "adityaprojects25@gmail.com"  # Your email address
    receiver_email = "adityaprojects25@gmail.com"  # Same email address to receive messages
    password = "dyjv ajtx wqvk fbub"  # Use the App Password here

    # Create the email
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Send the email
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, password)
            server.send_message(msg)
    except Exception as e:
        print(f"Error sending email: {e}")


@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('view_users'))

if __name__ == '__main__':
    # create_table()
    app.run(debug=True)

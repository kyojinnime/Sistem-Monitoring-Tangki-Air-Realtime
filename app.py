from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response
import mysql.connector
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import plotly.graph_objs as go
import plotly.utils
import json
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io
import base64

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  

# Konfigurasi Database
db_config = {
    'host': 'localhost',
    'user': 'root',  
    'password': '',  
    'database': 'water_level'
}

def get_db_connection():
    """Menghubungkan ke Database"""
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

def init_db():
    """Initialize database with sample data if tables are empty"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if mesin table has data
        cursor.execute("SELECT COUNT(*) FROM mesin")
        mesin_count = cursor.fetchone()[0]
        
        if mesin_count == 0:
            # Insert sample machines
            sample_mesin = [
                ('M001', 'Pompa Air Utama', 'Gedung A'),
                ('M002', 'Pompa Cadangan', 'Gedung B'),
                ('M003', 'Monitor Tangki', 'Gedung C')
            ]
            cursor.executemany(
                "INSERT INTO mesin (id_mesin, nama_mesin, lokasi) VALUES (%s, %s, %s)", 
                sample_mesin
            )
        
        # Check if users table has data
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        if user_count == 0:
            # Insert default admin user
            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                ('admin', 'admin@example.com', 'admin123')
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Database initialized successfully")
        
    except mysql.connector.Error as err:
        print(f"Database initialization error: {err}")
#Login
@app.route('/')
def index():
    """Pindah ke Halaman Login"""
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Halaman Login"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, email FROM users WHERE username = %s AND password = %s", 
                (username, password)
            )
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user:
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['email'] = user[2]
                flash('Login berhasil!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Username atau password salah!', 'error')
        else:
            flash('Koneksi database gagal!', 'error')
    
    return render_template('login.html')

#Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Halaman Register"""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id FROM users WHERE username = %s OR email = %s", 
                (username, email)
            )
            existing_user = cursor.fetchone()
            
            if existing_user:
                flash('Username atau email sudah terdaftar!', 'error')
            else:
                cursor.execute(
                    "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                    (username, email, password)
                )
                conn.commit()
                flash('Registrasi berhasil! Silakan login.', 'success')
                cursor.close()
                conn.close()
                return redirect(url_for('login'))
            
            cursor.close()
            conn.close()
        else:
            flash('Koneksi database gagal!', 'error')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    """User Logout"""
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

#Dashboard
@app.route('/dashboard')
def dashboard():
    """Halaman Dashboard"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu!', 'error')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    stats = {}
    
    if conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM mesin")
        stats['total_machines'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM waterlevel")
        stats['total_records'] = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT m.nama_mesin, w.ketinggian, w.status, w.waktu
            FROM waterlevel w
            JOIN mesin m ON w.id_mesin = m.id_mesin
            ORDER BY w.waktu DESC
            LIMIT 5
        """)
        stats['latest_readings'] = cursor.fetchall()
        
        cursor.execute("""
            SELECT m.id_mesin, m.nama_mesin, m.lokasi, 
                   COALESCE(MAX(w.ketinggian), 0) as latest_level,
                   COALESCE(MAX(w.status), 'No Data') as latest_status
            FROM mesin m
            LEFT JOIN waterlevel w ON m.id_mesin = w.id_mesin
            GROUP BY m.id_mesin, m.nama_mesin, m.lokasi
        """)
        stats['machines'] = cursor.fetchall()
        
        cursor.close()
        conn.close()
    
    return render_template('dashboard.html', stats=stats)

#Monitoring Water Level
@app.route('/monitoring_water')
def monitoring_water():
    """Water monitoring page"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu!', 'error')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    machines = []
    
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_mesin, nama_mesin, lokasi FROM mesin")
        machines = cursor.fetchall()
        cursor.close()
        conn.close()
    
    return render_template('monitoring_water.html', machines=machines)

@app.route('/get_water_data/<machine_id>')
def get_water_data(machine_id):
    """Get water level data for specific machine (AJAX endpoint)"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor()
    
    # Get last 24 hours data
    cursor.execute("""
        SELECT ketinggian, status, waktu 
        FROM waterlevel 
        WHERE id_mesin = %s AND waktu >= NOW() - INTERVAL 24 HOUR
        ORDER BY waktu ASC
    """, (machine_id,))
    
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # Format data for Chart.js
    chart_data = {
        'labels': [row[2].strftime('%H:%M') for row in data],
        'data': [row[0] for row in data],
        'status': [row[1] for row in data]
    }
    
    return jsonify(chart_data)

#Halaman Add Machine
@app.route('/add_machine', methods=['GET', 'POST'])
def add_machine():
    """Add machine page"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu!', 'error')
        return redirect(url_for('login'))
    
    # Get machines data for display in table
    conn = get_db_connection()
    machines = []
    
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_mesin, nama_mesin, lokasi FROM mesin ORDER BY id_mesin")
        machines = cursor.fetchall()
        cursor.close()
        conn.close()
    
    if request.method == 'POST':
        id_mesin = request.form['id_mesin']
        nama_mesin = request.form['nama_mesin']
        lokasi = request.form['lokasi']
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute(
                    "INSERT INTO mesin (id_mesin, nama_mesin, lokasi) VALUES (%s, %s, %s)",
                    (id_mesin, nama_mesin, lokasi)
                )
                conn.commit()
                flash('Mesin berhasil ditambahkan!', 'success')
                return redirect(url_for('add_machine'))  # Redirect to refresh data
            except mysql.connector.IntegrityError:
                flash('ID Mesin sudah ada!', 'error')
            except Exception as e:
                flash(f'Error: {str(e)}', 'error')
            
            cursor.close()
            conn.close()
        else:
            flash('Koneksi database gagal!', 'error')
    
    return render_template('add_machine.html', machines=machines)

@app.route('/edit_machine/<machine_id>', methods=['GET', 'POST'])
def edit_machine(machine_id):
    """Edit machine page"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu!', 'error')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn:
        flash('Koneksi database gagal!', 'error')
        return redirect(url_for('add_machine'))
    
    cursor = conn.cursor()
    
    if request.method == 'POST':
        nama_mesin = request.form['nama_mesin']
        lokasi = request.form['lokasi']
        
        try:
            cursor.execute(
                "UPDATE mesin SET nama_mesin = %s, lokasi = %s WHERE id_mesin = %s",
                (nama_mesin, lokasi, machine_id)
            )
            conn.commit()
            flash('Mesin berhasil diperbarui!', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        
        cursor.close()
        conn.close()
        return redirect(url_for('add_machine'))
    
    # GET request - get machine data
    cursor.execute("SELECT id_mesin, nama_mesin, lokasi FROM mesin WHERE id_mesin = %s", (machine_id,))
    machine = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not machine:
        flash('Mesin tidak ditemukan!', 'error')
        return redirect(url_for('add_machine'))
    
    return render_template('edit_machine.html', machine=machine)

@app.route('/delete_machine/<machine_id>', methods=['POST'])
def delete_machine(machine_id):
    """Delete machine"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection failed'}), 500
    
    cursor = conn.cursor()
    
    try:
        # Check if machine has water level records
        cursor.execute("SELECT COUNT(*) FROM waterlevel WHERE id_mesin = %s", (machine_id,))
        record_count = cursor.fetchone()[0]
        
        if record_count > 0:
            # Delete water level records first
            cursor.execute("DELETE FROM waterlevel WHERE id_mesin = %s", (machine_id,))
        
        # Delete machine
        cursor.execute("DELETE FROM mesin WHERE id_mesin = %s", (machine_id,))
        conn.commit()
        
        if cursor.rowcount > 0:
            return jsonify({'success': True, 'message': 'Mesin berhasil dihapus!'})
        else:
            return jsonify({'success': False, 'message': 'Mesin tidak ditemukan!'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

#Export PDF
@app.route('/export_pdf', methods=['GET', 'POST'])
def export_pdf():
    """Export PDF page"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu!', 'error')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    machines = []
    
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_mesin, nama_mesin FROM mesin")
        machines = cursor.fetchall()
        cursor.close()
        conn.close()
    
    if request.method == 'POST':
        machine_id = request.form['machine_id']
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        
        return generate_pdf_report(machine_id, start_date, end_date)
    
    return render_template('export_pdf.html', machines=machines)

def generate_pdf_report(machine_id, start_date, end_date):
    """Generate PDF report for machine data"""
    conn = get_db_connection()
    if not conn:
        flash('Koneksi database gagal!', 'error')
        return redirect(url_for('export_pdf'))
    
    cursor = conn.cursor()
    
    # Get machine info
    cursor.execute("SELECT nama_mesin, lokasi FROM mesin WHERE id_mesin = %s", (machine_id,))
    machine_info = cursor.fetchone()
    
    # Get data within date range
    cursor.execute("""
        SELECT ketinggian, status, waktu 
        FROM waterlevel 
        WHERE id_mesin = %s AND DATE(waktu) BETWEEN %s AND %s
        ORDER BY waktu DESC
    """, (machine_id, start_date, end_date))
    
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title = Paragraph(f"Water Level Report - {machine_info[0]}", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 12))
    
    # Machine details
    details = Paragraph(f"<b>Machine ID:</b> {machine_id}<br/><b>Location:</b> {machine_info[1]}<br/><b>Date Range:</b> {start_date} to {end_date}", styles['Normal'])
    story.append(details)
    story.append(Spacer(1, 12))
    
    # Data table
    if data:
        table_data = [['Water Level', 'Status', 'Time']]
        for row in data:
            table_data.append([
                f"{row[0]:.2f} cm",
                row[1],
                row[2].strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        table = Table(table_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
    else:
        no_data = Paragraph("No data found for the selected date range.", styles['Normal'])
        story.append(no_data)
    
    doc.build(story)
    buffer.seek(0)
    
    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=water_report_{machine_id}_{start_date}_{end_date}.pdf'
    
    return response

@app.route('/api/get_preview_data', methods=['POST'])
def get_preview_data():
    """Get preview data for selected machine and date range"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    machine_id = data['machine_id']
    start_date = data['start_date']
    end_date = data['end_date']
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection failed'}), 500
    
    cursor = conn.cursor()
    
    # Get data within date range
    cursor.execute("""
        SELECT ketinggian, status, waktu 
        FROM waterlevel 
        WHERE id_mesin = %s AND DATE(waktu) BETWEEN %s AND %s
        ORDER BY waktu DESC
        LIMIT 100
    """, (machine_id, start_date, end_date))
    
    data_results = cursor.fetchall()
    
    if data_results:
        # Calculate summary
        levels = [float(row[0]) for row in data_results]
        summary = {
            'total_records': len(data_results),
            'avg_level': sum(levels) / len(levels),
            'max_level': max(levels),
            'min_level': min(levels)
        }
        
        # Format data
        formatted_data = []
        for row in data_results:
            formatted_data.append({
                'ketinggian': float(row[0]),
                'status': row[1],
                'waktu': row[2].strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({
            'success': True,
            'data': formatted_data,
            'summary': summary
        })
    else:
        return jsonify({
            'success': False,
            'data': [],
            'message': 'No data found'
        })
    
    cursor.close()
    conn.close()
    
# API endpoint to add water level data (for testing/simulation)
@app.route('/api/add_water_data', methods=['POST'])
def add_water_data():
    """API endpoint to add water level data"""
    try:
        data = request.get_json()
        machine_id = data['machine_id']
        ketinggian = data['ketinggian']
        status = data['status']
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO waterlevel (id_mesin, ketinggian, status) VALUES (%s, %s, %s)",
                (machine_id, ketinggian, status)
            )
            conn.commit()
            cursor.close()
            conn.close()
            
            return jsonify({'success': True, 'message': 'Data added successfully'})
        else:
            return jsonify({'success': False, 'message': 'Database connection failed'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

if __name__ == '__main__':
    init_db()  # Initialize database with sample data
    app.run(debug=True, host='0.0.0.0', port=5000)


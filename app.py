import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'pavani_pickles_secret'
DB_PATH = os.path.join(os.path.dirname(__name__), 'database.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT DEFAULT 'user'
                 )''')
    # Products Table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    price REAL NOT NULL,
                    image TEXT,
                    category TEXT
                 )''')
    # Orders Table
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    total_amount REAL,
                    status TEXT DEFAULT 'Pending',
                    payment_method TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                 )''')
    # Cart Items / Order Items
    c.execute('''CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER,
                    product_id INTEGER,
                    quantity INTEGER,
                    price REAL,
                    FOREIGN KEY(order_id) REFERENCES orders(id),
                    FOREIGN KEY(product_id) REFERENCES products(id)
                 )''')
    # Insert dummy products if empty
    c.execute('SELECT COUNT(*) FROM products')
    if c.fetchone()[0] == 0:
        c.executemany('INSERT INTO products (name, description, price, image, category) VALUES (?, ?, ?, ?, ?)', [
            ('Spicy Mango Pickle', 'Traditional Aavakaaya from Andhra, rich in taste and spice.', 250, 'mango_pickle.png', 'mango'),
            ('Tangy Lemon Pickle', 'Aged lemon pickle with a perfect blend of tanginess and spice.', 200, 'lemon_pickle.png', 'lemon'),
            ('Garlic Pickle', 'Pungent and extremely flavorful garlic cloves infused in spicy oil.', 280, 'garlic_pickle.png', 'spicy')
        ])
    
    # Create an admin user if not exists
    c.execute('SELECT COUNT(*) FROM users WHERE email = "admin@pavani.com"')
    if c.fetchone()[0] == 0:
        pw_hash = generate_password_hash("admin123")
        c.execute('INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)', 
                  ("Admin", "admin@pavani.com", pw_hash, "admin"))

    conn.commit()
    conn.close()

with app.app_context():
    init_db()

@app.route('/')
def index():
    conn = get_db()
    products = conn.execute('SELECT * FROM products LIMIT 3').fetchall()
    conn.close()
    return render_template('index.html', featured_products=products)

@app.route('/products')
def products():
    category = request.args.get('category')
    conn = get_db()
    if category:
        products = conn.execute('SELECT * FROM products WHERE category = ? COLLATE NOCASE OR name LIKE ?', (category, f'%{category}%')).fetchall()
    else:
        products = conn.execute('SELECT * FROM products').fetchall()
    conn.close()
    return render_template('products.html', products=products, search=category)

@app.route('/product/<int:id>')
def product_details(id):
    conn = get_db()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (id,)).fetchone()
    conn.close()
    if not product:
        return "Product not found", 404
    return render_template('product_details.html', product=product)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            flash('Login successful!', 'success')
            if user['role'] == 'admin':
                return redirect(url_for('admin'))
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials, please try again.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        pw_hash = generate_password_hash(password)
        
        conn = get_db()
        try:
            conn.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, pw_hash))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists.', 'error')
        finally:
            conn.close()
            
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/api/cart', methods=['GET', 'POST', 'DELETE'])
def cart_api():
    if 'cart' not in session:
        session['cart'] = {}
        
    if request.method == 'GET':
        return jsonify(session['cart'])
        
    if request.method == 'POST':
        data = request.json
        product_id = str(data['product_id'])
        quantity = data.get('quantity', 1)
        if product_id in session['cart']:
            session['cart'][product_id]['quantity'] += quantity
        else:
            session['cart'][product_id] = {
                'name': data['name'],
                'price': data['price'],
                'image': data['image'],
                'quantity': quantity
            }
        session.modified = True
        return jsonify({'success': True, 'cart': session['cart']})
        
    if request.method == 'DELETE':
        data = request.json
        product_id = str(data['product_id'])
        if product_id in session['cart']:
            del session['cart'][product_id]
            session.modified = True
        return jsonify({'success': True, 'cart': session['cart']})
        
@app.route('/cart')
def cart_page():
    cart = session.get('cart', {})
    total = sum(item['price'] * item['quantity'] for item in cart.values())
    return render_template('cart.html', cart=cart, total=total)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        flash('Please login to continue checkout.', 'warning')
        return redirect(url_for('login'))
        
    cart = session.get('cart', {})
    if not cart:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('products'))
        
    total = sum(item['price'] * item['quantity'] for item in cart.values())
    
    if request.method == 'POST':
        payment_method = request.form['payment_method']
        # Mock payment processing here
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO orders (user_id, total_amount, status, payment_method) VALUES (?, ?, ?, ?)', 
                       (session['user_id'], total, 'Success', payment_method))
        order_id = cursor.lastrowid
        
        for p_id, item in cart.items():
            cursor.execute('INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)',
                           (order_id, p_id, item['quantity'], item['price']))
            
        conn.commit()
        conn.close()
        session['cart'] = {} # Clear cart
        flash('Payment successful! Order placed.', 'success')
        return redirect(url_for('orders_dashboard'))
        
    return render_template('checkout.html', total=total)

@app.route('/orders')
def orders_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db()
    orders = conn.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('orders.html', orders=orders)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('user_role') != 'admin':
        flash('Unauthorized access', 'error')
        return redirect(url_for('index'))
        
    conn = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form['name']
            price = request.form['price']
            desc = request.form['description']
            category = request.form['category']
            image = request.files['image']
            img_filename = image.filename if image else 'default.png'
            if image:
                image.save(os.path.join(app.root_path, 'static/images', img_filename))
            conn.execute('INSERT INTO products (name, description, price, image, category) VALUES (?, ?, ?, ?, ?)',
                         (name, desc, price, img_filename, category))
        elif action == 'delete':
            product_id = request.form['product_id']
            conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
        conn.commit()

    products = conn.execute('SELECT * FROM products').fetchall()
    orders = conn.execute('SELECT o.*, u.name as user_name FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.created_at DESC').fetchall()
    conn.close()
    return render_template('admin.html', products=products, orders=orders)

if __name__ == '__main__':
    app.run(debug=True, port=5000)

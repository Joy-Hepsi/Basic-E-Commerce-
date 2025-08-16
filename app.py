# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# ====== Flask & Upload Config ======
app.secret_key = "your_secret_key_change_me"
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ====== MySQL (XAMPP) Connection ======
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",      # XAMPP default
        password="",      # XAMPP default (empty)
        database="ecommerce_db",
    )

# ====== Public Pages ======
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/products")
def products():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name, description, price, image_url FROM products ORDER BY id DESC")
    items = cur.fetchall()
    conn.close()
    return render_template("products.html", products=items)

# ====== Cart (session-based) ======
@app.route("/add_to_cart/<int:product_id>")
def add_to_cart(product_id):
    # fetch a single product
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name, price, image_url FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()
    conn.close()

    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    # Ensure JSON serializable types in session (Decimal -> float)
    item = {
        "id": int(product["id"]),
        "name": product["name"],
        "price": float(product["price"] if product["price"] is not None else 0.0),
        "image_url": product["image_url"] or "",
    }

    cart = session.get("cart", [])
    cart.append(item)  # simple approach (duplicates allowed)
    session["cart"] = cart
    flash("Added to cart.", "success")
    return redirect(url_for("view_cart"))

@app.route("/cart")
def view_cart():
    cart_items = session.get("cart", [])
    total = sum(float(x.get("price", 0.0)) for x in cart_items)
    return render_template("cart.html", cart_items=cart_items, total=total)

@app.route("/remove_from_cart/<int:product_id>")
def remove_from_cart(product_id):
    cart = session.get("cart", [])
    # remove only the first matching occurrence to mimic "one item" removal
    removed = False
    new_cart = []
    for item in cart:
        if not removed and item.get("id") == product_id:
            removed = True
            continue
        new_cart.append(item)
    session["cart"] = new_cart
    flash("Removed from cart." if removed else "Item not found in cart.", "info")
    return redirect(url_for("view_cart"))

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart_items = session.get("cart", [])
    if not cart_items:
        flash("Your cart is empty.", "info")
        return redirect(url_for("view_cart"))

    total = sum(float(item.get('price', 0)) for item in cart_items)  # ✅ calculate total

    if request.method == "POST":
        name = request.form.get('name')
        email = request.form.get('email')
        address = request.form.get('address')
        phone = request.form.get('phone')
        payment_method = request.form.get('payment_method')

        session['order_info'] = {
            'name': name,
            'email': email,
            'address': address,
            'phone': phone,
            'payment_method': payment_method,
            'total': total,
            'items': cart_items
        }
        return redirect(url_for('order_confirmation'))

    return render_template("checkout.html", cart_items=cart_items, total=total)  # ✅ pass total



@app.route("/order_confirmation")
def order_confirmation():
    info = session.get("order_info", None)
    if not info:
        flash("No order information found.", "error")
        return redirect(url_for("checkout"))

    return render_template("confirmation.html", order_info=info)

 


# ====== Admin: Product List / Add / Delete ======
@app.route("/admin/products")
def admin_product_list():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name, description, price, image_url FROM products ORDER BY id DESC")
    products = cur.fetchall()
    conn.close()
    return render_template("admin_product_list.html", products=products)

@app.route("/admin/add_product", methods=["GET", "POST"])
def admin_add_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price_raw = request.form.get("price", "0").strip()
        image_file = request.files.get("image")

        # validation
        try:
            price = float(price_raw)
        except ValueError:
            price = 0.0

        image_url = ""
        if image_file and image_file.filename and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            image_file.save(save_path)
            # store relative path (under /static)
            image_url = f"uploads/{filename}"
        elif image_file and image_file.filename:
            flash("Unsupported image type. Use png/jpg/jpeg/webp/gif", "error")
            return redirect(url_for("admin_add_product"))

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO products (name, description, price, image_url) VALUES (%s, %s, %s, %s)",
            (name, description, price, image_url),
        )
        conn.commit()
        conn.close()

        flash("Product added.", "success")
        return redirect(url_for("admin_product_list"))

    return render_template("admin_add_product.html")

@app.route("/admin/delete_product/<int:product_id>")
def delete_product(product_id):
    # (Optional) Remove image file from disk if you want:
    # Fetch image_url first
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT image_url FROM products WHERE id = %s", (product_id,))
    row = cur.fetchone()
    # Delete row
    cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    conn.close()

    # If you want to also delete the image file:
    if row and row.get("image_url"):
        path = os.path.join("static", row["image_url"])
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception:
            # ignore filesystem errors
            pass

    flash("Product deleted.", "info")
    return redirect(url_for("admin_product_list"))

# ====== Run ======
if __name__ == "__main__":
    # Make sure to: pip install flask mysql-connector-python
    app.run(debug=True)
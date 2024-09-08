import os
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, Float
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from forms import RegisterForm, LoginForm, ServiceForm
import stripe

STRIPE_SECRET_KEY="sk_test_51PvbEC04pOucmjJHEtkF9EHpe2Jjrwr5Yo1vSu3sOLrHPDDHKhiIo0wGXb6up9QdOosalCAmw0AZuTydZvd0cinT009Zig0WLI"
STRIPE_PUBLISHABLE_KEY="pk_test_51PvbEC04pOucmjJHdtTkbLCfkt3SrPW0w6ORrTeBssZA37oUdpuW7TMU0mOK4a5ESEO3ZPm7UeFGM17LaNOF8ReT002SBnycoV"

stripe.api_key = STRIPE_SECRET_KEY


app = Flask(__name__)
app.config['SECRET_KEY'] = "8BYkEfBA6O6donzffWlSihBXox7C0sKR6b"
Bootstrap5(app)
login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


# CREATE DATABASE
class Base(DeclarativeBase):
    pass


app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///services.db"

db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class Services(db.Model):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(1000))
    cart_product = relationship("Cart", back_populates="user")


class Cart(UserMixin, db.Model):
    __tablename__ = "cart"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    user = relationship("User", back_populates="cart_product")
    service_id: Mapped[str] = mapped_column(Integer, db.ForeignKey("services.id"))
    title: Mapped[str] = mapped_column(String(250), db.ForeignKey("services.title"))
    description: Mapped[str] = mapped_column(Text, db.ForeignKey("services.description"))
    price: Mapped[float] = mapped_column(Float, db.ForeignKey("services.price"))
    img_url: Mapped[str] = mapped_column(String(250), db.ForeignKey("services.img_url"))
    quantity: Mapped[int] = mapped_column(Integer)


with app.app_context():
    db.create_all()


def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data
        result = db.session.execute(db.select(User).where(User.email == email))

        user = result.scalar()
        if user:
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))

        hash_and_salted_password = generate_password_hash(
            form.password.data,
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = User(
            email=form.email.data,
            password=hash_and_salted_password,
            name=form.name.data,
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for("get_all_services"))
    return render_template("register.html", form=form, logged_in=current_user.is_authenticated)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, password):
            flash('Password incorrect, please try again.')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('get_all_services'))
    return render_template("login.html", form=form, logged_in=current_user.is_authenticated)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_services'))


@app.route('/')
def get_all_services():
    result = db.session.execute(db.select(Services))
    services = result.scalars().all()
    return render_template("index.html", all_services=services, logged_in=current_user.is_authenticated)


@app.route("/service/<int:service_id>", methods=["GET", "POST"])
def show_service(service_id):
    requested_service = db.get_or_404(Services, service_id)
    return render_template("service.html", service=requested_service, current_user=current_user,
                           logged_in=current_user.is_authenticated)


@app.route("/add-cart/<int:service_id>", methods=['GET', 'POST'])
@login_required
def add_cart(service_id):
    quantity = int(request.form['quantity'])
    title = request.args.get('title')
    description = request.args.get('description')
    price = request.args.get('price')
    img_url = request.args.get('img_url')
    new_cart_product = Cart(
        user=current_user,
        service_id=service_id,
        title=title,
        description=description,
        price=price,
        img_url=img_url,
        quantity=quantity
    )
    db.session.add(new_cart_product)
    db.session.commit()
    return redirect(url_for('get_all_services', user=current_user, logged_in=current_user.is_authenticated))


@app.route("/cart/")
@login_required
def cart():
    total_price = 0
    result = db.session.execute(db.select(Cart).where(Cart.user_id == current_user.id))
    user_cart = result.scalars().all()
    for product in user_cart:
        total_price += product.price
    return render_template("cart.html", products=user_cart, user=current_user, price=total_price, logged_in=current_user.is_authenticated)


@app.route("/delete/<int:service_id>")
@login_required
def delete_product(service_id):
    service_to_delete = db.get_or_404(Cart, service_id)
    db.session.delete(service_to_delete)
    db.session.commit()
    return redirect(url_for('cart', user=current_user, logged_in=current_user.is_authenticated))


@app.route("/delete_complete/<int:service_id>")
@login_required
def delete_product_completely(service_id):
    service_to_delete = db.get_or_404(Services, service_id)
    db.session.delete(service_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_services', user=current_user, logged_in=current_user.is_authenticated))


@app.route("/new-service", methods=["GET", "POST"])
@admin_only
def add_new_service():
    form = ServiceForm()
    if form.validate_on_submit():
        new_service = Services(
            title=form.title.data,
            description=form.description.data,
            price=form.price.data,
            img_url=form.img_url.data
        )
        db.session.add(new_service)
        db.session.commit()
        create_stripe_product(form.title.data, int(form.price.data/100))
        return redirect(url_for("get_all_services", logged_in=current_user.is_authenticated))
    return render_template("make-service.html", form=form, logged_in=current_user.is_authenticated)


@app.route("/edit-service/<int:service_id>", methods=["GET", "POST"])
@admin_only
def edit_service(service_id):
    service = db.get_or_404(Services, service_id)
    edit_form = ServiceForm(
        title=service.title,
        description=service.description,
        img_url=service.img_url,
        price=service.price
    )
    if edit_form.validate_on_submit():
        service.title = edit_form.title.data
        service.description = edit_form.description.data
        service.img_url = edit_form.img_url.data
        service.price = edit_form.price.data
        db.session.commit()
        return redirect(url_for("get_all_services", logged_in=current_user.is_authenticated))
    return render_template("make-service.html", form=edit_form, is_edit=True, logged_in=current_user.is_authenticated)


@app.route("/about")
def about():
    return render_template("about.html", logged_in=current_user.is_authenticated)


@app.route("/contact")
def contact():
    return render_template("contact.html", logged_in=current_user.is_authenticated)


def create_stripe_product(product_name, price_in_cent):
    product = stripe.Product.create(name=product_name)
    price = stripe.Price.create(
        product=product.id,
        unit_amount=price_in_cent,
        currency='ils',
    )
    return price.id


@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    user_cart = Cart.query.filter_by(user_id=current_user.id).all()

    line_items = []
    for item in user_cart:
        line_items.append({
            'price_data': {
                'currency': 'ils',
                'product_data': {
                    'name': item.title,
                },
                'unit_amount': int(item.price * 100),
            },
            'quantity': item.quantity,
        })

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        success_url=url_for('payment_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=url_for('payment_cancelled', _external=True),
    )
    return redirect(session.url, code=303)


@app.route('/payment-success')
@login_required
def payment_success():
    session_id = request.args.get('session_id')
    session = stripe.checkout.Session.retrieve(session_id)

    result = db.session.execute(db.select(Cart).where(Cart.user_id == current_user.id))
    cart_to_delete = result.scalars().all()
    for product in cart_to_delete:
        db.session.delete(product)
        db.session.commit()

    flash('Payment successful!', 'success')
    return redirect(url_for('get_all_services', logged_in=current_user.is_authenticated, user=current_user))


@app.route('/payment-cancelled')
@login_required
def payment_cancelled():
    flash('Payment cancelled', 'warning')
    return redirect(url_for('get_all_services)', logged_in=current_user.is_authenticated, user=current_user))


if __name__ == "__main__":
    app.run(debug=False, port=5001)

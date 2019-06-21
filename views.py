from datetime import datetime
import requests
from flask import make_response
import json
import os
import httplib2
from oauth2client.client import FlowExchangeError
from oauth2client.client import flow_from_clientsecrets
from flask import session as login_session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, relationship, joinedload
from sqlalchemy.ext.declarative import declarative_base
from models import Base, Restaurant, MenuItem, Users
from flask import Flask, render_template, request
from flask import redirect, jsonify, url_for, flash

engine = create_engine('sqlite:///restaurant.db?check_same_thread=False')
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()

app = Flask(__name__)


# Login using google provider
@app.route('/oauth/<provider>', methods=['POST'])
def login(provider):
    """ Implementation of google authentication & authorization
    Args:
      provider: takes the name of the provider like google
    Returns:
       http response from google
    """
    # STEP 1 - Parse the auth code

    client_secret = (os.path.join(os.path.dirname(os.path.abspath(
        __file__)), 'client_secrets.json')).replace('\\', '/')

    auth_code = request.data
    print("Step 1 - Complete, received auth code %s" % auth_code)
    if provider == 'google':
        # STEP 2 - Exchange for a token
        try:
            # Upgrade the authorization code into a credentials object
            oauth_flow = flow_from_clientsecrets(client_secret, scope='')
            oauth_flow.redirect_uri = 'postmessage'
            credentials = oauth_flow.step2_exchange(auth_code)
        except FlowExchangeError:
            response = make_response(json.dumps(
                'Failed to upgrade the authorization code.'), 401)
            response.headers['Content-Type'] = 'application/json'
            return response

        # Check that the access token is valid.
        access_token = credentials.access_token
        url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
               % access_token)
        h = httplib2.Http()
        result = json.loads(h.request(url, 'GET')[1])
        # If there was an error in the access token info, abort.
        if result.get('error') is not None:
            response = make_response(json.dumps(result.get('error')), 500)
            response.headers['Content-Type'] = 'application/json'

        # # Verify that the access token is used for the intended user.
        gplus_id = credentials.id_token['sub']
        if result['user_id'] != gplus_id:
            response = make_response(json.dumps(
                "Token's user ID doesn't match given user ID."), 401)
            response.headers['Content-Type'] = 'application/json'
            return response

        # # Verify that the access token is valid for this app.
        CLIENT_ID = json.loads(open(client_secret, 'r').read())[
            'web']['client_id']
        if result['issued_to'] != CLIENT_ID:
            response = make_response(json.dumps(
                "Token's client ID does not match app's."), 401)
            response.headers['Content-Type'] = 'application/json'
            return response

        stored_credentials = login_session.get('credentials')
        stored_gplus_id = login_session.get('gplus_id')
        if stored_credentials is not None and gplus_id == stored_gplus_id:
            response = make_response(json.dumps(
                'Current user is already connected.'), 200)
            response.headers['Content-Type'] = 'application/json'
            return response

        # Store the access token in the session for later use.
        login_session['access_token'] = credentials.access_token
        login_session['gplus_id'] = gplus_id

        print("Step 2 Complete! Access Token : %s " % credentials.access_token)

        # STEP 3 - Find User or make a new one

        # Get user info
        h = httplib2.Http()
        userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
        params = {'access_token': credentials.access_token, 'alt': 'json'}
        answer = requests.get(userinfo_url, params=params)

        data = answer.json()

        login_session['name'] = data['name']
        login_session['picture'] = data['picture']
        login_session['email'] = data['email']

        print('User Name: %s' % login_session['name'])
        print('User Email: %s' % login_session['email'])

        # return redirect('/restaurants')
        # see if user exists, if it doesn't make a new one
        user = session.query(Users).filter_by(
            email=login_session['email']).first()
        if not user:
            user = Users(
                name=login_session['name'], picture=login_session['picture'],
                email=login_session['email'], category="2")

            session.add(user)
            session.commit()
            print('User is registered successfully!')
        else:
            print('User Exists')

        login_session['user_id'] = user.id
        login_session['category'] = "2"

        output = ''
        output += login_session['name']
        output += login_session['picture']
        return output

        # return redirect(url_for('home'))
    else:
        return 'Unrecoginized Provider'


@app.route('/logout')
def logout():
    if login_session['category'] == "2":
        access_token = login_session['access_token']
        if access_token is None:
            response = make_response(
                json.dumps('Current user not connected.'), 401)
            response.headers['Content-Type'] = 'application/json'
            return response
        url = ('https://accounts.google.com/o/oauth2/revoke?token=%s' %
               access_token)
        h = httplib2.Http()
        result = h.request(uri=url, method='POST', body=None,
                           headers={'content-type':
                                    'application/x-www-form-urlencoded'})[0]

        if result['status'] == '200':
            del login_session['access_token']
            del login_session['name']
            del login_session['email']
            del login_session['picture']
            del login_session['user_id']
            del login_session['category']
            response = make_response(json.dumps(
                'Successfully disconnected.'), 200)
            response.headers['Content-Type'] = 'application/json'
            flash("Successfully signed out from google account", "success")
            return redirect('/home')
        else:
            response = make_response(
                json.dumps('Failed to revoke token for given user.'), 400)
            response.headers['Content-Type'] = 'application/json'
            return response
    else:
        del login_session['name']
        del login_session['email']
        del login_session['user_id']
        del login_session['category']
        flash("Successfully signed out", "success")
        return redirect('/home')


# Signup page
@app.route('/signup')
def signup_page():
    return redirect(url_for('register_user'))


# Login Page
@app.route('/login', methods=['GET', 'POST'])
def login_user():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        print('email: %s' % email)
        print('password: %s' % password)

        user = session.query(Users).filter_by(email=email).first()
        if not user:

            print('User or Password is incorrect!')
            flash('User or Password is incorrect!.', "danger")
            return redirect('/login')
        else:
            print('User is successfully logged in!')
            flash('User is successfully logged in!', "success")
            login_session['name'] = user.name
            login_session['user_id'] = user.id
            login_session['email'] = user.email
            login_session['category'] = user.category
            return redirect('/home')
    else:
        return render_template(
            'signin.html',
            title='Login',
            year=datetime.now().year,
            message='The restaurant catalog'
        )


# Register User
@app.route('/register-user', methods=["GET", "POST"])
def register_user():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        print('name: %s' % name)
        print('email: %s' % email)
        print('password: %s' % password)

        user = session.query(Users).filter_by(email=email).first()
        if not user:
            new_user = Users(name=name, email=email,
                             password=password, category="2")
            session.add(new_user)
            session.commit()
            print('User is registered successfully!')
            flash('User is successfully registered.', "success")
        else:
            print('User Exists')
            flash('User already registered!', "success")

        return redirect('/login')
    else:
        return render_template('signup.html')


# New restaurant registration
@app.route('/restaurant/new/', methods=['GET', 'POST'])
def register_restaurant():
    if 'name' not in login_session:
        return redirect('/login')
    user_id = login_session['user_id']
    if 'user_id' not in login_session:
        return redirect('/login')

    if request.method == 'POST':
        restaurant = Restaurant(
            name=request.form['restaurant-name'],
            user_id=login_session['user_id'])
        session.add(restaurant)
        flash('Restaurant is successfully registered.', "success")
        print('Restaurant is succesfully Added')
        session.commit()
        return redirect(url_for('list_all_restaurants'))
    else:
        return render_template('new_restaurant.html')


# Edit Restaurant
@app.route('/restaurant/<int:restaurant_id>/edit', methods=['GET', 'POST'])
def editRestaurant(restaurant_id):
    # check if username is logged in
    if 'name' not in login_session:
        return redirect('/login')
    editRestaurant = session.query(Restaurant).filter_by(
        id=restaurant_id).one()
    if editRestaurant.user_id != login_session['user_id']:
        flash('You do not have permission to edit it', "danger")
        return redirect(url_for('home'))
    if request.method == 'POST':
        if request.form['restaurant_name']:
            editRestaurant.name = request.form['restaurant_name']
            session.add(editRestaurant)
            session.commit()
            flash('Successfully Edited', 'success')
            return redirect(url_for('list_all_restaurants'))
    else:
        return render_template('edit_restaurant.html',
                               restaurant_id=restaurant_id,
                               editRestaurant=editRestaurant)


# Delete Restaurant
@app.route('/restaurant/<int:restaurant_id>/delete', methods=['GET', 'POST'])
def deleteRestaurant(restaurant_id):
    if 'name' not in login_session:
        return redirect('/login')
    delRestaurant = session.query(Restaurant).filter_by(
        id=restaurant_id).one()
    if delRestaurant.user_id != login_session['user_id']:
        flash('You do not have permission to delete it', "danger")
        return redirect(url_for('home'))
    if request.method == 'POST':
        session.delete(delRestaurant)
        session.commit()
        flash('Successfully Deleted', 'success')
        return redirect(url_for('list_all_restaurants'))
    else:
        return render_template('delete_restaurant.html',
                               delRestaurant=delRestaurant)


# JSON Restaurants View
@app.route('/json')
def AllRestaurantMenuJSON():
    restaurants = session.query(Restaurant).options(
        joinedload(Restaurant.items)).all()
    return jsonify(restaurants=[dict(c.serialize,
                                     items=[i.serialize for i in c.items])
                                for c in restaurants])


# JSON APIs to view a single Restaurant's Menu Information
@app.route('/restaurant/<int:restaurant_id>/menu/JSON')
def restaurantMenuJSON(restaurant_id):
    """ JSON APIs to view a single Restaurant's Menu Information """
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    items = session.query(MenuItem).filter_by(
        restaurant_id=restaurant_id).all()
    return jsonify(MenuItems=[i.serialize for i in items])


# JSON APIs to view a menu Information
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/JSON')
def menuItemJSON(restaurant_id, menu_id):
    """ JSON APIs to view a menu Information
    Args:
     restaurant_Id: the unique integer id for the restaurant
     menu_id: the unique integer id for the menu item

    Returns:
     Serialized json menu item
    """
    Menu_Item = session.query(MenuItem).filter_by(id=menu_id).one()
    return jsonify(Menu_Item=Menu_Item.serialize)


# JSON APIs to view restaurant Information
@app.route('/restaurant/JSON')
def restaurantsJSON():
    """ JSON APIs to view a menu Information
    Args:
     restaurant_Id: the unique integer id for the restaurant
     menu_id: the unique integer id for the menu item

    Returns:
     Serialized json menu item
    """
    restaurants = session.query(Restaurant).all()
    return jsonify(restaurants=[r.serialize for r in restaurants])


# Redirect to restaurants page
@app.route('/')
@app.route('/home')
def home():
    return redirect(url_for('list_all_restaurants'))


# List all restaurants
@app.route('/restaurants/')
def list_all_restaurants():
    restaurants = session.query(Restaurant).all()
    menus = session.query(MenuItem).all()
    return render_template('restaurants.html',
                           restaurants=restaurants, menus=menus)


# List all menus
@app.route('/restaurant/<int:restaurant_id>/')
@app.route('/restaurant/<int:restaurant_id>/menu/')
def list_all_menu(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(
        id=restaurant_id).one()
    items = session.query(MenuItem).filter_by(
        restaurant_id=restaurant_id).all()
    return render_template('menus.html', items=items,
                           restaurant=restaurant)


# view restaurant menu items
@app.route('/restaurant/<string:restaurant_name>/menu/')
def view_restaurant(restaurant_name):
    restaurants = session.query(Restaurant).all()
    restaurant = session.query(Restaurant).filter_by(
        name=restaurant_name).one()

    items = session.query(MenuItem).filter_by(
        restaurant_id=restaurant.id).all()

    count = session.query(MenuItem).filter_by(
        restaurant_id=restaurant.id).count()

    return render_template('view_restaurant.html', items=items,
                           restaurants=restaurants,
                           res_name=restaurant_name, countitem=count)


# View Menu item
@app.route('/restaurant/<string:restaurant_name>/<string:menu_name>/')
def view_menu(restaurant_name, menu_name):
    restaurant = session.query(Restaurant).filter_by(
        name=restaurant_name).one()
    item = session.query(MenuItem).filter_by(
        name=menu_name).one()
    return render_template('view_menu.html', item=item, restaurant=restaurant)


# Create a new menu item
@app.route('/restaurant/<int:restaurant_id>/menu/new/',
           methods=['GET', 'POST'])
def add_menu(restaurant_id):
    if 'name' not in login_session:
        return redirect('/login')
    user_id = login_session['user_id']
    if request.method == 'POST':
        if restaurant_id == "":
            flash('Please select a restaurant name.', "danger")
            return render_template('new_menu.html',
                                   restaurant_id=restaurant_id)
        restaurant = session.query(
            Restaurant).filter_by(id=restaurant_id).one()
        if restaurant.user_id != login_session['user_id']:
            flash("You don't have permission to add a menu", "danger")
            return redirect(url_for('home'))
        newMenu = MenuItem(name=request.form['name'],
                           description=request.form['description'],
                           price=request.form['price'],
                           restaurant_id=restaurant_id,
                           user_id=user_id)
        session.add(newMenu)
        flash('New Menu %s Item Successfully Added' %
              (newMenu.name), "success")
        session.commit()
        return redirect(url_for('list_all_menu', restaurant_id=restaurant_id))
    else:
        return render_template('new_menu.html', restaurant_id=restaurant_id)


# Edit menu
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/edit',
           methods=['GET', 'POST'])
def edit_menu(restaurant_id, menu_id):

    if 'name' not in login_session:
        return redirect('/login')

    menuItem = session.query(MenuItem).filter_by(id=menu_id).one()
    if menuItem.user_id != login_session['user_id']:
        flash('You do not have permission to edit it.', "danger")
        return redirect(url_for('list_all_menu', restaurant_id=restaurant_id))

    editedItem = session.query(MenuItem).filter_by(id=menu_id).one()
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        session.add(editedItem)
        session.commit()
        flash('Menu Item Successfully Edited', 'success')
        return redirect(url_for('list_all_menu', restaurant_id=restaurant_id))
    else:
        return render_template('edit_menu.html', restaurant_id=restaurant_id,
                               menu_id=menu_id, menuItem=editedItem)


# Delete Menu
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/delete',
           methods=['GET', 'POST'])
def delete_menu(restaurant_id, menu_id):

    if 'name' not in login_session:
        return redirect('/login')

    menuItem = session.query(MenuItem).filter_by(id=menu_id).one()
    if menuItem.user_id != login_session['user_id']:
        flash('You do not have permission to delete it.', "danger")
        return redirect(url_for('list_all_menu', restaurant_id=restaurant_id))

    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    itemToDelete = session.query(MenuItem).filter_by(id=menu_id).one()
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Menu Item Successfully Deleted', 'success')
        return redirect(url_for('list_all_menu', restaurant_id=restaurant_id))
    else:
        return render_template('delete_menu.html', menuItem=itemToDelete)


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)

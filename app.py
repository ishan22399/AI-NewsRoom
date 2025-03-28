from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import json
from sqlite3 import Connection as SQLite3Connection
from sqlalchemy import event
from sqlalchemy.engine import Engine
import requests
from datetime import datetime, timedelta
import random
from newspaper import Article as NewspaperArticle
from nltk.tokenize import sent_tokenize
import nltk
import hashlib  # Add this import at the top with your other imports
# Test script to verify installation
import lxml.html.clean
print("lxml.html.clean successfully imported!")

from newspaper import Article as NewspaperArticle
print("newspaper module successfully imported!")

# Make sure to download NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

# Configure your news API key - Replace with your own API key
NEWS_API_KEY = "d9277e7cb3344bf891670ffd861ba03b"  # from newsapi.org

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///newsroom.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Configure SQLite to enforce foreign key constraints
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    full_name = db.Column(db.String(100))
    timezone = db.Column(db.String(50), default="utc+0")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    profile_image = db.Column(db.String(200), default="default.jpg")
    
    # Relationships
    chats = db.relationship('Chat', backref='user', lazy=True)
    preferences = db.relationship('UserPreference', backref='user', uselist=False, lazy=True)
    rewards = db.relationship('Reward', backref='user', uselist=False, lazy=True)
    interests = db.relationship('UserInterest', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    messages = db.relationship('Message', backref='chat', lazy=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_user = db.Column(db.Boolean, default=True)  # True if from user, False if from AI
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class UserPreference(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    
    # AI Assistant preferences
    response_style = db.Column(db.String(20), default="balanced")  # concise, balanced, detailed
    include_images = db.Column(db.Boolean, default=True)
    include_visualizations = db.Column(db.Boolean, default=True)
    include_sources = db.Column(db.Boolean, default=True)
    trusted_sources_only = db.Column(db.Boolean, default=False)
    
    # News feed preferences
    news_frequency = db.Column(db.String(20), default="hourly")
    content_limit = db.Column(db.Integer, default=10)
    
    # Notification preferences
    email_breaking_news = db.Column(db.Boolean, default=True)
    email_daily_digest = db.Column(db.Boolean, default=True)
    email_account_updates = db.Column(db.Boolean, default=True)
    email_product_updates = db.Column(db.Boolean, default=False)
    
    push_breaking_news = db.Column(db.Boolean, default=True)
    push_topic_updates = db.Column(db.Boolean, default=True)
    push_chat_responses = db.Column(db.Boolean, default=False)
    
    enable_quiet_hours = db.Column(db.Boolean, default=True)
    quiet_hours_start = db.Column(db.String(5), default="22:00")
    quiet_hours_end = db.Column(db.String(5), default="07:00")
    
    # Privacy settings
    allow_analytics = db.Column(db.Boolean, default=True)
    allow_personalization = db.Column(db.Boolean, default=True)
    store_chat_history = db.Column(db.Boolean, default=True)

class UserInterest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    interest = db.Column(db.String(50), nullable=False)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'interest', name='unique_user_interest'),)

class Reward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    points = db.Column(db.Integer, default=0)
    level = db.Column(db.String(20), default="News Explorer")
    last_daily_points = db.Column(db.Date)
    streak_days = db.Column(db.Integer, default=0)

class RewardHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text)
    image_url = db.Column(db.String(500))
    source = db.Column(db.String(100))
    author = db.Column(db.String(100))
    published_at = db.Column(db.DateTime)
    category = db.Column(db.String(50))
    url = db.Column(db.String(500), unique=True)
    ai_summary = db.Column(db.Text)
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'image_url': self.image_url,
            'source': self.source,
            'author': self.author,
            'published_at': self.published_at.strftime("%B %d, %Y") if self.published_at else None,
            'category': self.category,
            'url': self.url,
            'ai_summary': self.ai_summary,
            'read_time': calculate_read_time(self.content or '')
        }

class ArticleView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    article_id = db.Column(db.String(255), nullable=False)  # Store as string to handle hash IDs
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ArticleUrl(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.String(255), unique=True, nullable=False)
    url = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    # Fix deprecation warning by using db.session.get instead of query.get
    return db.session.get(User, int(user_id))

# Helper functions
def add_points(user_id, points, action):
    """Add points to user's rewards and create history entry"""
    reward = Reward.query.filter_by(user_id=user_id).first()
    if reward:
        reward.points += points
        
        # Determine level based on points
        if reward.points >= 3000:
            reward.level = "News Virtuoso"
        elif reward.points >= 1500:
            reward.level = "News Analyst"
        elif reward.points >= 500:
            reward.level = "News Insider"
        else:
            reward.level = "News Explorer"
    
    # Log the reward history
    history = RewardHistory(user_id=user_id, points=points, action=action)
    db.session.add(history)
    db.session.commit()

def get_ai_response(message):
    """Generate a simple AI response based on the input message"""
    if "headline" in message.lower() or "top news" in message.lower():
        return "Today's top headlines include developments in global politics, breakthroughs in renewable energy technology, and major economic policy changes. Would you like details on any specific topic?"
    elif "crypto" in message.lower():
        return "The cryptocurrency market has been experiencing significant volatility lately. Bitcoin and Ethereum have shown mixed trends, while regulatory news continues to influence investor sentiment."
    elif "tech" in message.lower():
        return "Recent tech news highlights include advancements in AI technology, new product launches from major tech companies, and ongoing discussions about digital privacy regulation."
    else:
        return f"I'm processing your request about: {message}. This is a simulated response as the AI news integration is still in development."

# Add helper functions for news retrieval and summarization
def fetch_news_for_interests(interests, count=10):
    """Fetch news articles based on user interests"""
    if not interests:
        interests = ["general"]  # Default if no interests
    
    articles = []
    for interest in interests:
        try:
            url = f"https://newsapi.org/v2/everything?q={interest}&apiKey={NEWS_API_KEY}&pageSize=5&language=en&sortBy=publishedAt"
            response = requests.get(url)
            data = response.json()
            
            if data.get("status") == "ok" and data.get("articles"):
                for article in data.get("articles"):
                    # Add category to the article
                    article["category"] = interest
                    articles.append(article)
        except Exception as e:
            print(f"Error fetching news for {interest}: {e}")
            continue
    
    # Limit articles and sort by date
    return sorted(articles[:count], key=lambda x: x.get("publishedAt", ""), reverse=True)

def summarize_article(url, max_sentences=3):
    """Generate a summary of an article from its URL"""
    try:
        # Change Article to NewspaperArticle here
        article = NewspaperArticle(url)
        article.download()
        article.parse()
        
        # Use NLTK to extract key sentences
        sentences = sent_tokenize(article.text)
        return " ".join(sentences[:max_sentences]) if sentences else "No summary available."
    except:
        return "Unable to generate summary."

# Mock data for trending topics visualization
def get_trending_topics():
    topics = [
        {"name": "Technology", "percentage": 32, "trend": 5, "color": "#4f46e5", "icon": "microchip"},
        {"name": "Business", "percentage": 28, "trend": -2, "color": "#06b6d4", "icon": "chart-line"},
        {"name": "Health", "percentage": 20, "trend": 8, "color": "#10b981", "icon": "heartbeat"},
        {"name": "Politics", "percentage": 15, "trend": 3, "color": "#f59e0b", "icon": "landmark"},
        {"name": "Science", "percentage": 12, "trend": 1, "color": "#8b5cf6", "icon": "flask"}
    ]
    return topics

# Add these functions to the "Helper Functions" section of your app.py
# (around line 150, before your route definitions)

def generate_ai_summary(article_data):
    """Generate an AI summary of the article."""
    try:
        text = article_data.get('content', '') or article_data.get('description', '')
        if len(text) < 100:
            return "This article provides insights on the latest developments in this field."
        
        # Extract first few sentences for a summary
        sentences = sent_tokenize(text)[:3]
        summary = " ".join(sentences)
        return summary
    except:
        return "This article explores key developments in technology and innovation."

def get_related_articles(article_data, count=3):
    """Get related articles based on the current article."""
    related_articles = []
    
    try:
        # Extract keywords from article title
        title_words = article_data.get('title', '').split()
        search_terms = [word for word in title_words if len(word) > 3][:3]
        
        if not search_terms:
            search_terms = ["technology", "news"]
        
        search_query = '+'.join(search_terms)
        
        # Get related articles from API
        response = requests.get(
            f"https://newsapi.org/v2/everything?q={search_query}&apiKey={NEWS_API_KEY}&pageSize={count+2}",
            timeout=10
        )
        
        if response.status_code == 200:
            results = response.json()
            if results.get('status') == "ok" and results.get('articles'):
                for article in results['articles']:
                    # Skip if it's the same article
                    if article.get('title') == article_data.get('title'):
                        continue
                        
                    # Create related article object
                    related = {
                        'id': str(hash(article.get('url', ''))),
                        'title': article.get('title', 'Related Article'),
                        'summary': article.get('description', 'No description available.'),
                        'image_url': article.get('urlToImage', 'https://via.placeholder.com/400x200/4f46e5/ffffff?text=Related+Article'),
                        'source': article.get('source', {}).get('name', 'Unknown Source'),
                        'published_at': format_date(article.get('publishedAt')),
                        'url': article.get('url', '#')
                    }
                    related_articles.append(related)
                    
                    if len(related_articles) >= count:
                        break
    except Exception as e:
        app.logger.error(f"Error getting related articles: {str(e)}")
    
    # Fill with placeholders if needed
    while len(related_articles) < count:
        idx = len(related_articles) + 1
        related_articles.append({
            'id': f"placeholder-{idx}",
            'title': f"Related Technology Article {idx}",
            'summary': "Explore more related content on AI Newsroom.",
            'image_url': f"https://via.placeholder.com/400x200/4f46e5/ffffff?text=Related+Article+{idx}",
            'source': "AI Newsroom",
            'published_at': "Recently",
            'url': url_for('dashboard')
        })
    
    return related_articles

# Add this function at the top of your helper functions section
def ensure_valid_image_url(url):
    """Ensure the image URL is valid and has a proper protocol."""
    if not url:  # Handle None or empty string
        return 'https://via.placeholder.com/800x450/4f46e5/ffffff?text=AI+Newsroom'
        
    # Convert URL to string if it's another type
    url = str(url)
    
    # Fix URLs without protocol
    if url.startswith('//'):
        return f"https:{url}"
    
    # Ensure URL has a protocol
    if not url.startswith(('http://', 'https://')):
        return f"https://{url}"
        
    return url

# Replace the hash generation in news_category and elsewhere with this function
def generate_stable_id(url):
    """Generate a stable ID for an article URL using MD5."""
    if not url:
        return "no-url-" + str(random.randint(1000, 9999))
    return hashlib.md5(url.encode('utf-8')).hexdigest()

# Add this helper function with your other helper functions

def store_article_url(article_id, url):
    """Store article URL in database instead of session."""
    # Check if entry already exists
    existing = ArticleUrl.query.filter_by(article_id=article_id).first()
    if (existing):
        existing.url = url
    else:
        article_url = ArticleUrl(article_id=article_id, url=url)
        db.session.add(article_url)
    db.session.commit()

# Routes
@app.route('/')
def index():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))
        
        # Create new user
        new_user = User(username=username, email=email, full_name=full_name)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        # Create user preferences
        preferences = UserPreference(user_id=new_user.id)
        db.session.add(preferences)
        
        # Create rewards entry
        rewards = Reward(user_id=new_user.id)
        db.session.add(rewards)
        
        # Add default interests
        interests = ['Technology', 'Business']
        for interest in interests:
            user_interest = UserInterest(user_id=new_user.id, interest=interest)
            db.session.add(user_interest)
        
        db.session.commit()
        
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            
            # Check if this is the first login of the day for rewards
            reward = Reward.query.filter_by(user_id=user.id).first()
            today = datetime.now().date()
            
            if reward.last_daily_points != today:
                # First login of the day - award points
                add_points(user.id, 5, "Daily login")
                
                # Update streak
                if reward.last_daily_points and (today - reward.last_daily_points).days == 1:
                    reward.streak_days += 1
                    
                    # Award streak bonus every 5 days
                    if reward.streak_days % 5 == 0:
                        add_points(user.id, 15, f"{reward.streak_days} day streak bonus")
                else:
                    reward.streak_days = 1
                
                reward.last_daily_points = today
                db.session.commit()
            
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        # Fetch user reward data or create if not exists
        reward = Reward.query.filter_by(user_id=current_user.id).first()
        if not reward:
            reward = Reward(
                user_id=current_user.id,
                points=0,
                streak_days=0,
                level="News Explorer",
                last_daily_points=datetime.now().date()
            )
            db.session.add(reward)
            db.session.commit()
        
        # Get user's interest topics
        user_interests = [interest.interest for interest in UserInterest.query.filter_by(user_id=current_user.id).all()]
        if not user_interests:
            # Create default interests if none exist
            default_interests = ['Technology', 'Business', 'Science']
            for interest in default_interests:
                new_interest = UserInterest(user_id=current_user.id, interest=interest)
                db.session.add(new_interest)
            db.session.commit()
            user_interests = default_interests
        
        # Get recent chats
        chats = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.timestamp.desc()).limit(5).all()
        
        # Get current date
        current_date = datetime.now().strftime("%B %d, %Y")
        
        # Initialize variables needed by template
        article_urls = {}
        top_stories = []
        recommended_articles = []
        articles_trend = 0  # Default trend value
        articles_read_today = 0
        articles_read_week = 0
        
        # Fetch news from the API
        try:
            # Top stories
            top_stories_response = requests.get(
                f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}&pageSize=6",
                timeout=10
            )
            if top_stories_response.status_code == 200:
                top_stories = top_stories_response.json().get('articles', [])
            else:
                top_stories = []  # Ensure it's an empty list, not None
                
            # Recommended articles based on user interests
            recommended_query = '+OR+'.join(user_interests)
            recommended_response = requests.get(
                f"https://newsapi.org/v2/everything?q={recommended_query}&apiKey={NEWS_API_KEY}&pageSize=6&sortBy=relevancy",
                timeout=10
            )
            if recommended_response.status_code == 200:
                recommended_articles = recommended_response.json().get('articles', [])
            else:
                recommended_articles = []  # Ensure it's an empty list, not None
                
        except Exception as e:
            app.logger.error(f"Error fetching news: {str(e)}")
            flash('Error loading news data. Please try again later.', 'warning')
            # Ensure we have empty lists instead of None
            top_stories = []
            recommended_articles = []
        
        # Get trending topics
        trending_topics = get_trending_topics()
        
        # Process all articles to add consistent IDs and enhance data
        news_articles = (top_stories or []) + (recommended_articles or [])
        
        for article in news_articles:
            if not article or not article.get('url'):
                continue
                
            # Generate a consistent ID based on the URL using MD5
            article_id = generate_stable_id(article.get('url', ''))
            article['id'] = article_id
            
            # Store URL in database instead of session
            store_article_url(article_id, article.get('url'))
            
            # Process dates for display
            if article.get('publishedAt'):
                try:
                    date_obj = datetime.fromisoformat(article['publishedAt'].replace('Z', '+00:00'))
                    article['published_at'] = date_obj.strftime("%B %d, %Y")
                except Exception:
                    article['published_at'] = 'Recently'
            else:
                article['published_at'] = 'Recently'
            
            # Ensure image URL is available - safely handle None
            article['urlToImage'] = ensure_valid_image_url(article.get('urlToImage'))
            
            # Calculate read time (estimated) - safely handle None values
            content = article.get('content') or ''
            description = article.get('description') or ''
            content_length = len(str(content) if content else str(description))
            article['read_time'] = max(1, content_length // 800)  # ~200 words per minute, ~4 chars per word
        
        # Get articles read statistics
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        articles_read_today = ArticleView.query.filter(
            ArticleView.user_id == current_user.id,
            db.func.date(ArticleView.timestamp) == today
        ).count()
        
        articles_read_week = ArticleView.query.filter(
            ArticleView.user_id == current_user.id,
            ArticleView.timestamp >= week_ago
        ).count()
        
        # Calculate trend (can be positive or negative)
        yesterday = today - timedelta(days=1)
        articles_read_yesterday = ArticleView.query.filter(
            ArticleView.user_id == current_user.id,
            db.func.date(ArticleView.timestamp) == yesterday
        ).count()
        
        articles_trend = articles_read_today - articles_read_yesterday
                
        # Store article URLs in session for retrieval
        session['article_urls'] = article_urls
        session['top_stories'] = top_stories
        session['recommended_articles'] = recommended_articles
        
        # Add this at the end of the dashboard route, before the return statement
        # Remove large data from session to prevent cookie size issues
        if 'article_urls' in session:
            del session['article_urls']
        if 'top_stories' in session:
            del session['top_stories']
        if 'recommended_articles' in session:
            del session['recommended_articles']
        
        # Return the dashboard template with all required data
        return render_template('dashboard.html', 
                          reward=reward, 
                          chats=chats or [],
                          top_stories=top_stories or [],
                          recommended_articles=recommended_articles or [],
                          trending_topics=trending_topics,
                          user_topics=user_interests,
                          current_date=current_date,
                          articles_read_today=articles_read_today,
                          articles_read_week=articles_read_week,
                          articles_trend=articles_trend)
    
    except Exception as e:
        app.logger.error(f"Dashboard error: {str(e)}")
        flash(f'Error loading dashboard: {str(e)}', 'danger')
        
        # Create default empty reward object to prevent None errors
        default_reward = Reward(
            user_id=current_user.id,  # Make sure we use current_user.id
            points=0,
            streak_days=0,
            level="News Explorer",
            last_daily_points=datetime.now().date()
        )
        
        # Ensure all required variables are defined
        return render_template('dashboard.html', 
                          reward=default_reward,
                          chats=[],
                          top_stories=[],
                          recommended_articles=[],
                          trending_topics=get_trending_topics(),
                          user_topics=[],
                          current_date=datetime.now().strftime("%B %d, %Y"),
                          articles_read_today=0,
                          articles_read_week=0,
                          articles_trend=0,
                          articles_read=0,  # Add this missing variable
                          articles_per_day=[0, 0, 0, 0, 0, 0, 0])  # Add this missing variable

# Helper function to calculate read time
def calculate_read_time(content):
    """Calculate estimated reading time in minutes."""
    if not content:  # Handle None or empty content
        return 1
    
    # Average reading speed: 200-250 words per minute
    word_count = len(str(content).split())
    return max(1, round(word_count / 225))

# Add these new routes after your dashboard route

@app.route('/news/<category>')
@login_required
def news_category(category):
    """Show all news articles for a specific category."""
    import requests  # Make sure this is imported
    
    try:
        # Get user's interest topics
        user_interests = [interest.interest for interest in 
                         UserInterest.query.filter_by(user_id=current_user.id).all()]
        if not user_interests:
            # Default interests if user hasn't selected any
            user_interests = ['Indian Politics', 'Technology', 'Science', 'Astronaut', 'Technology']
        
        # Set default articles for display
        articles = []
        
        # Get the articles based on category
        if category == 'top':
            # If top stories aren't in session, fetch them
            top_stories = session.get('top_stories')
            if not top_stories:
                try:
                    # Fetch top headlines
                    response = requests.get(
                        f"https://newsapi.org/v2/top-headlines?country=in&apiKey={NEWS_API_KEY}&pageSize=20",
                        timeout=10
                    )
                    if response.status_code == 200:
                        top_stories = response.json().get('articles', [])
                        session['top_stories'] = top_stories
                    else:
                        top_stories = []
                except Exception as e:
                    app.logger.error(f"Error fetching top stories: {str(e)}")
                    top_stories = []
            
            articles = top_stories
            title = "Top Stories"
            description = "The most important news stories of the day"
            
        elif category == 'recommended':
            # If recommended articles aren't in session, generate them
            recommended_articles = session.get('recommended_articles')
            if not recommended_articles:
                # Use interests to fetch personalized articles
                recommended_articles = []
                
                # Fetch articles for each interest
                for interest in user_interests[:3]:  # Limit to first 3 interests
                    try:
                        response = requests.get(
                            f"https://newsapi.org/v2/everything?q={interest}&apiKey={NEWS_API_KEY}&pageSize=5&sortBy=relevancy",
                            timeout=10
                        )
                        if response.status_code == 200:
                            interest_articles = response.json().get('articles', [])
                            # Add to recommended list
                            recommended_articles.extend(interest_articles)
                        else:
                            # If API fails, try with a different interest
                            continue
                    except Exception as e:
                        app.logger.error(f"Error fetching recommended articles for {interest}: {str(e)}")
                        continue
                
                # Shuffle articles to mix different interests
                from random import shuffle
                shuffle(recommended_articles)
                
                # Limit to 20 articles
                recommended_articles = recommended_articles[:20]
                
                # Store in session
                session['recommended_articles'] = recommended_articles
            
            articles = recommended_articles
            title = "Recommended For You"
            description = "Articles tailored to your interests"
            
        else:
            # Handle category-specific news
            try:
                response = requests.get(
                    f"https://newsapi.org/v2/everything?q={category}&apiKey={NEWS_API_KEY}&pageSize=20&sortBy=relevancy",
                    timeout=10
                )
                if response.status_code == 200:
                    articles = response.json().get('articles', [])
                else:
                    articles = []
            except Exception as e:
                app.logger.error(f"Error fetching category news: {str(e)}")
                articles = []
                
            title = f"{category.capitalize()} News"
            description = f"Latest news about {category}"
        
        # Ensure articles is not None and handle empty list
        if articles is None:
            articles = []
            
        # Process articles
        processed_articles = []
        for article in articles:
            if not article:
                continue
                
            if not article.get('url'):
                continue
                
            # Generate a consistent ID based on the URL
            article_id = generate_stable_id(article.get('url', ''))
            article['id'] = article_id
            
            # Process dates for display
            if article.get('publishedAt'):
                try:
                    from datetime import datetime
                    date_obj = datetime.fromisoformat(article['publishedAt'].replace('Z', '+00:00'))
                    article['published_at'] = date_obj.strftime("%B %d, %Y")
                except Exception:
                    article['published_at'] = 'Recently'
            else:
                article['published_at'] = 'Recently'
            
            # Ensure image URL is available
            if not article.get('urlToImage') or "null" in str(article.get('urlToImage')).lower() or "default.jpg" in str(article.get('urlToImage')).lower():
                # Placeholder image by category
                if category == 'technology':
                    article['urlToImage'] = 'https://via.placeholder.com/400x225/4f46e5/ffffff?text=Technology'
                elif category == 'science':
                    article['urlToImage'] = 'https://via.placeholder.com/400x225/10b981/ffffff?text=Science'
                elif 'politics' in category:
                    article['urlToImage'] = 'https://via.placeholder.com/400x225/ef4444/ffffff?text=Politics'
                elif category == 'top':
                    article['urlToImage'] = 'https://via.placeholder.com/400x225/6366f1/ffffff?text=Top+Stories'
                elif category == 'recommended':
                    article['urlToImage'] = 'https://via.placeholder.com/400x225/8b5cf6/ffffff?text=Recommended'
                else:
                    article['urlToImage'] = f'https://via.placeholder.com/400x225/4f46e5/ffffff?text={category.capitalize()}'
            else:
                # Ensure URL has proper protocol and absolute path
                url = article.get('urlToImage', '')
                article['urlToImage'] = ensure_valid_image_url(url)
                
                # Additional check for relative paths
                if not article['urlToImage'].startswith(('http://', 'https://')):
                    article['urlToImage'] = f'https://via.placeholder.com/400x225/6366f1/ffffff?text=Top+Story'
            
            # Calculate read time
            content = article.get('content') or ''
            description = article.get('description') or ''
            content_length = len(str(content) if content else str(description))
            article['read_time'] = max(1, content_length // 800)
            
            # Add to processed articles
            processed_articles.append(article)
            
            # Store URL in database
            store_article_url(article_id, article.get('url'))
        
        # Handle case where we still don't have articles after processing
        if not processed_articles:
            # Create sample articles based on the user's interests for demo purposes
            sample_articles = []
            
            topics = user_interests + ['Top Story', 'Breaking News'] if category == 'top' else user_interests
            
            for i, topic in enumerate(topics[:10]):
                sample_articles.append({
                    'id': f'sample-{i}',
                    'title': f'{topic} News: Important Development in {topic}',
                    'description': f'This is a sample article about {topic}. In a production environment, this would be replaced with real content from the News API.',
                    'urlToImage': f'https://via.placeholder.com/400x225/{["4f46e5", "10b981", "ef4444", "f59e0b", "6366f1"][i % 5]}/ffffff?text={topic.replace(" ", "+")}',
                    'source': {'name': 'Sample News Source'},
                    'published_at': 'Today',
                    'read_time': 3,
                    'url': '#'
                })
            
            processed_articles = sample_articles
                
        return render_template('news_category.html', 
                              articles=processed_articles,
                              title=title,
                              description=description,
                              user_topics=user_interests,
                              category=category)
                              
    except Exception as e:
        app.logger.error(f"Category view error: {str(e)}")
        flash(f'Error loading news: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/api/articles/read-complete', methods=['POST'])
@login_required
def article_read_complete():
    """Track when a user completes reading an article."""
    try:
        data = request.json
        article_id = data.get('article_id')
        
        if not article_id:
            return jsonify({'success': False, 'message': 'Article ID is required'}), 400
        
        # Check if the article exists in our database
        article_url_obj = ArticleUrl.query.filter_by(article_id=article_id).first()
        if not article_url_obj:
            return jsonify({'success': False, 'message': 'Article not found'}), 404
        
        # Check if the user has already completed this article today
        today = datetime.now().date()
        existing_completion = ArticleView.query.filter(
            ArticleView.user_id == current_user.id,
            ArticleView.article_id == article_id,
            db.func.date(ArticleView.timestamp) == today
        ).first()
        
        if not existing_completion:
            # Add new view to track completion
            article_view = ArticleView(
                user_id=current_user.id,
                article_id=article_id,
                timestamp=datetime.now()
            )
            db.session.add(article_view)
            
            # Add bonus points for completing an article
            add_points(current_user.id, 3, "Completed reading an article")
            
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': 'Article completion recorded',
                'points_awarded': 3
            })
        else:
            # Already completed today, just update the timestamp
            existing_completion.timestamp = datetime.now()
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': 'Article completion updated',
                'points_awarded': 0
            })
            
    except Exception as e:
        app.logger.error(f"Error recording article completion: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/topics')
@login_required
def topics():
    """Show all trending topics page."""
    try:
        # Get trending topics
        trending_topics = get_trending_topics()
        
        # Get user's interest topics
        user_interests = [interest.interest for interest in 
                         UserInterest.query.filter_by(user_id=current_user.id).all()]
        
        # For each topic, get a few articles
        topic_articles = {}
        for topic in trending_topics:
            try:
                response = requests.get(
                    f"https://newsapi.org/v2/everything?q={topic['name']}&apiKey={NEWS_API_KEY}&pageSize=4&sortBy=relevancy",
                    timeout=10
                )
                if response.status_code == 200:
                    articles = response.json().get('articles', [])
                    for article in articles:
                        if article.get('url'):
                            article['id'] = generate_stable_id(article.get('url', ''))
                            article['urlToImage'] = ensure_valid_image_url(article.get('urlToImage'))
                    topic_articles[topic['name']] = articles
                else:
                    topic_articles[topic['name']] = []
            except Exception as e:
                app.logger.error(f"Error fetching topic articles: {str(e)}")
                topic_articles[topic['name']] = []
        
        return render_template('topics.html',
                             trending_topics=trending_topics,
                             topic_articles=topic_articles,
                             user_topics=user_interests)
                             
    except Exception as e:
        app.logger.error(f"Topics view error: {str(e)}")
        flash(f'Error loading topics: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    data = request.json
    message = data.get('message')
    
    # Create a new chat if it's the first message
    chat_id = session.get('current_chat_id')
    if not chat_id:
        new_chat = Chat(user_id=current_user.id)
        db.session.add(new_chat)
        db.session.flush()  # Get the ID without committing
        chat_id = new_chat.id
        session['current_chat_id'] = chat_id
    
    # Store user message
    user_message = Message(
        chat_id=chat_id,
        content=message,
        is_user=True
    )
    db.session.add(user_message)
    
    # Generate and store AI response
    ai_response = get_ai_response(message)
    ai_message = Message(
        chat_id=chat_id,
        content=ai_response,
        is_user=False
    )
    db.session.add(ai_message)
    db.session.commit()
    
    # Award points for chat interaction (once per chat)
    if session.get('points_awarded_for_chat') != chat_id:
        add_points(current_user.id, 2, "Chat interaction")
        session['points_awarded_for_chat'] = chat_id
    
    return jsonify({
        'response': ai_response
    })

@app.route('/api/feedback', methods=['POST'])
@login_required
def api_feedback():
    # Award points for providing feedback
    add_points(current_user.id, 2, "Provided feedback")
    
    # In a real app, you would store the actual feedback
    return jsonify({'success': True})

@app.route('/api/share', methods=['POST'])
@login_required
def api_share():
    # Award points for sharing content
    add_points(current_user.id, 10, "Shared content")
    
    return jsonify({'success': True})

@app.route('/rewards')
@login_required
def rewards():
    reward = Reward.query.filter_by(user_id=current_user.id).first()
    
    # Calculate progress to next level
    next_level_points = 500  # Default for News Explorer
    if reward.level == "News Explorer":
        next_level_points = 500
        progress = min(reward.points / 500 * 100, 100)
        next_level = "News Insider"
    elif reward.level == "News Insider":
        next_level_points = 1500
        progress = min((reward.points - 500) / 1000 * 100, 100)
        next_level = "News Analyst"
    elif reward.level == "News Analyst":
        next_level_points = 3000
        progress = min((reward.points - 1500) / 1500 * 100, 100)
        next_level = "News Virtuoso"
    else:  # News Virtuoso
        next_level_points = reward.points  # Already at max level
        progress = 100
        next_level = "News Virtuoso"
    
    # Get reward history
    history = RewardHistory.query.filter_by(user_id=current_user.id).order_by(RewardHistory.timestamp.desc()).limit(10).all()
    
    return render_template('rewards.html', 
                          reward=reward, 
                          progress=progress,
                          next_level=next_level,
                          next_level_points=next_level_points,
                          history=history)

@app.route('/settings')
@login_required
def settings():
    preferences = UserPreference.query.filter_by(user_id=current_user.id).first()
    interests = [interest.interest for interest in UserInterest.query.filter_by(user_id=current_user.id).all()]
    
    return render_template('settings.html', 
                          preferences=preferences,
                          interests=interests)

@app.route('/api/settings/profile', methods=['POST'])
@login_required
def update_profile():
    data = request.form
    
    # Update user profile
    current_user.full_name = data.get('fullname')
    current_user.username = data.get('username')
    current_user.email = data.get('email')
    current_user.timezone = data.get('timezone')
    
    # Update interests
    UserInterest.query.filter_by(user_id=current_user.id).delete()
    interests = request.form.getlist('interests')
    for interest in interests:
        user_interest = UserInterest(user_id=current_user.id, interest=interest)
        db.session.add(user_interest)
    
    db.session.commit()
    flash('Profile updated successfully')
    return redirect(url_for('settings'))

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            # In a real application, you would send a password reset email
            flash('Password reset email sent')
            return redirect(url_for('login'))
        else:
            flash('Email not found')
    
    return render_template('reset_password.html')

@app.route('/api/settings/password', methods=['POST'])
@login_required
def update_password():
    current_password = request.form.get('current-password')
    new_password = request.form.get('new-password')
    confirm_password = request.form.get('confirm-password')
    
    if not current_user.check_password(current_password):
        flash('Current password is incorrect')
        return redirect(url_for('settings'))
    
    if new_password != confirm_password:
        flash('New passwords do not match')
        return redirect(url_for('settings'))
    
    current_user.set_password(new_password)
    db.session.commit()
    flash('Password updated successfully')
    return redirect(url_for('settings'))

@app.route('/api/settings/preferences', methods=['POST'])
@login_required
def update_preferences():
    data = request.form
    pref = UserPreference.query.filter_by(user_id=current_user.id).first()
    
    # Update AI preferences
    pref.response_style = data.get('response-style')
    pref.include_images = 'include_images' in data
    pref.include_visualizations = 'include_visualizations' in data
    pref.include_sources = 'include_sources' in data
    pref.trusted_sources_only = 'trusted_sources_only' in data
    
    # Update news feed preferences
    pref.news_frequency = data.get('news-frequency')
    pref.content_limit = int(data.get('content-limit'))
    
    db.session.commit()
    flash('AI preferences updated successfully')
    return redirect(url_for('settings'))

@app.route('/api/settings/notifications', methods=['POST'])
@login_required
def update_notifications():
    data = request.form
    pref = UserPreference.query.filter_by(user_id=current_user.id).first()
    
    # Update email notifications
    pref.email_breaking_news = 'breaking-news' in data
    pref.email_daily_digest = 'daily-digest' in data
    pref.email_account_updates = 'account-updates' in data
    pref.email_product_updates = 'product-updates' in data
    
    # Update push notifications
    pref.push_breaking_news = 'push-breaking-news' in data
    pref.push_topic_updates = 'push-topic-updates' in data
    pref.push_chat_responses = 'push-chat-responses' in data
    
    # Update quiet hours
    pref.enable_quiet_hours = 'enable-quiet-hours' in data
    pref.quiet_hours_start = data.get('quiet-start')
    pref.quiet_hours_end = data.get('quiet-end')
    
    db.session.commit()
    flash('Notification settings updated successfully')
    return redirect(url_for('settings'))

@app.route('/api/settings/privacy', methods=['POST'])
@login_required
def update_privacy():
    data = request.form
    pref = UserPreference.query.filter_by(user_id=current_user.id).first()
    
    # Update privacy settings
    pref.allow_analytics = 'usage-analytics' in data
    pref.allow_personalization = 'personalization' in data
    pref.store_chat_history = 'chat-history' in data
    
    db.session.commit()
    flash('Privacy settings updated successfully')
    return redirect(url_for('settings'))

@app.route('/api/settings/export-data')
@login_required
def export_data():
    # In a real application, you would generate a JSON file with user data
    # For this example, we'll just simulate the export
    return jsonify({
        'message': 'Data export initiated. You will receive an email with your data shortly.'
    })

@app.route('/api/settings/clear-history')
@login_required
def clear_history():
    # Delete all user's chat history
    chats = Chat.query.filter_by(user_id=current_user.id).all()
    for chat in chats:
        Message.query.filter_by(chat_id=chat.id).delete()
    
    Chat.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    
    return jsonify({
        'message': 'Chat history cleared successfully'
    })

@app.route('/api/redeem', methods=['POST'])
@login_required
def redeem_reward():
    data = request.json
    reward_id = data.get('reward_id')
    cost = data.get('cost')
    
    user_reward = Reward.query.filter_by(user_id=current_user.id).first()
    
    if user_reward.points < cost:
        return jsonify({
            'success': False,
            'message': 'Not enough points'
        })
    
    # Deduct points
    user_reward.points -= cost
    
    # Log redemption
    history = RewardHistory(
        user_id=current_user.id,
        points=-cost,
        action=f"Redeemed reward: {reward_id}"
    )
    db.session.add(history)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Reward redeemed successfully',
        'remaining_points': user_reward.points
    })

# Replace your article route with this fixed version
@app.route('/article/<article_id>')
@login_required
def article(article_id):
    try:
        # Get article URL from database
        article_url_obj = ArticleUrl.query.filter_by(article_id=article_id).first()
        
        # If not in database, try session as fallback
        if not article_url_obj:
            article_urls = session.get('article_urls', {})
            article_url = article_urls.get(article_id)
            
            # If not in session either, check if we have a view record
            if not article_url:
                article_view = ArticleView.query.filter_by(article_id=article_id).first()
                if article_view:
                    flash('Article found in history but URL needs to be refetched', 'info')
                else:
                    flash('Article not found or URL expired', 'warning')
                return redirect(url_for('dashboard'))
        else:
            article_url = article_url_obj.url
        
        # Initialize article data with defaults
        article = {
            'id': article_id,
            'title': 'Article not found',
            'content': '<p>The article content could not be loaded.</p>',
            'description': 'Article description not available',
            'author': 'Unknown',
            'published_at': datetime.now().strftime("%B %d, %Y"),
            'read_time': 3,
            'image_url': 'https://via.placeholder.com/1200x600/6366F1/FFFFFF?text=Article+Image',
            'source': {'name': 'Unknown Source'},
            'category': 'News',
            'tags': ['News']
        }
        
        # Try to fetch article details from API if URL exists
        try:
            # First try to get the article from NewsAPI metadata that was already fetched
            for article_list in [session.get('top_stories', []), session.get('recommended_articles', [])]:
                for article_item in article_list or []:
                    if generate_stable_id(article_item.get('url', '')) == article_id:
                        # Found article in cached data
                        article['title'] = article_item.get('title', article['title'])
                        article['description'] = article_item.get('description', article['description'])
                        article['author'] = article_item.get('author', article['author'])
                        article['image_url'] = article_item.get('urlToImage', article['image_url'])
                        article['source'] = article_item.get('source', article['source'])
                        article['published_at'] = article_item.get('published_at', article['published_at'])
                        article['content'] = article_item.get('content', article['description'])
                        break
            
            # If we have a URL, try to fetch full content with newspaper
            if article_url:
                try:
                    from newspaper import Article as NewsArticle
                    news_article = NewsArticle(article_url)
                    news_article.download()
                    news_article.parse()
                    
                    # Update article with detailed data
                    if news_article.title:
                        article['title'] = news_article.title
                    
                    if news_article.text:
                        # Convert plain text to HTML paragraphs
                        paragraphs = news_article.text.split('\n\n')
                        article['content'] = ''.join([f'<p>{p}</p>' for p in paragraphs if p.strip()])
                    
                    if news_article.top_image:
                        article['image_url'] = news_article.top_image
                        
                    if news_article.publish_date:
                        article['published_at'] = news_article.publish_date.strftime("%B %d, %Y")
                        
                    if news_article.authors:
                        article['author'] = news_article.authors[0] if news_article.authors else article['author']
                        
                    # Generate tags
                    article['tags'] = generate_tags(article['title'], article['description'])
                    
                except Exception as e:
                    app.logger.error(f"Error parsing article with newspaper: {str(e)}")
                    # Continue with metadata we have
            
            # Calculate read time based on content length
            article['read_time'] = calculate_read_time(article['content'])
                
        except Exception as e:
            app.logger.error(f"Error processing article: {str(e)}")
        
        # Record the article view for the user
        try:
            # Check if user has already viewed this article today
            today = datetime.now().date()
            existing_view = ArticleView.query.filter(
                ArticleView.user_id == current_user.id,
                ArticleView.article_id == article_id,
                db.func.date(ArticleView.timestamp) == today
            ).first()
            
            if not existing_view:
                # Add new view and award points only if first view today
                article_view = ArticleView(
                    user_id=current_user.id,
                    article_id=article_id,
                    timestamp=datetime.now()
                )
                db.session.add(article_view)
                
                # Add points for reading a new article
                add_points(current_user.id, 5, "Read an article")
                
                db.session.commit()
        except Exception as e:
            app.logger.error(f"Error recording article view: {str(e)}")
            db.session.rollback()
            
        # Get related articles
        try:
            related_articles = get_related_articles({
                'title': article['title'],
                'description': article['description']
            }, count=3)
        except:
            related_articles = []
            
        # Create a proper context for the template
        context = {
            'article': article,
            'related_articles': related_articles,
            'read_progress': 0,  # Initial reading progress
        }
        
        return render_template('article.html', **context)
    
    except Exception as e:
        app.logger.error(f"Article error: {str(e)}")
        flash('Error loading article. Please try again.', 'danger')
        return redirect(url_for('dashboard'))


# Add these helper functions
def process_content(content, description):
    """Process and expand article content for better display."""
    # Ensure we're working with strings, not None
    content = content or ""
    description = description or ""
    
    # If content is missing completely, use description
    if not content.strip():
        return description or "No content available for this article."
        
    # If content ends with [+N chars], it's truncated - clean it up
    if '[+' in content:
        base_content = content.split('[+')[0].strip()
        
        # Add description as additional context if available and not redundant
        if description and description not in base_content:
            full_content = f"{base_content}\n\n{description}"
            return full_content
        return base_content
    
    # Content is complete, return as is
    return content


def expand_article_content(content, description=None):
    """Expand article content to make it more readable."""
    if not content:
        return "No content available for this article."
        
    # If content is very short, try to add the description
    if len(content) < 200 and description:
        combined = f"{content}\n\n{description}"
        return combined
        
    # Break content into paragraphs if it's just a long block
    if len(content) > 300 and content.count('\n') < 2:
        sentences = sent_tokenize(content)
        paragraphs = []
        current_para = []
        
        for sentence in sentences:
            current_para.append(sentence)
            if len(' '.join(current_para)) > 150:
                paragraphs.append(' '.join(current_para))
                current_para = []
                
        if current_para:
            paragraphs.append(' '.join(current_para))
            
        return '\n\n'.join(paragraphs)
        
    return content


def calculate_read_time(content):
    """Calculate estimated reading time in minutes."""
    # Average reading speed: 200-250 words per minute
    word_count = len(content.split())
    return max(1, round(word_count / 225))


def generate_tags(title, description):
    """Generate article tags based on title and description."""
    # Combine title and description
    text = f"{title} {description}".lower()
    
    # List of common tech categories
    categories = [
        "AI", "Artificial Intelligence", "Machine Learning", "Technology", 
        "Business", "Innovation", "Science", "Data", "Cloud", "Security",
        "Mobile", "Apps", "Software", "Hardware", "Robotics", "Internet",
        "Social Media", "Digital", "Blockchain", "Cryptocurrency",
        "Gaming", "Health Tech", "Climate Tech", "Finance", "Startups"
    ]
    
    # Find matching categories
    tags = []
    for category in categories:
        if category.lower() in text or category.lower().replace(" ", "") in text:
            tags.append(category)
    
    # Add some default tags if we didn't find enough
    if len(tags) < 3:
        default_tags = ["Technology", "Innovation", "Digital"]
        for tag in default_tags:
            if tag not in tags:
                tags.append(tag)
                if len(tags) >= 5:
                    break
    
    return tags[:5]  # Return maximum 5 tags

def format_date(date_string):
    """Convert API date format to human-readable format."""
    if not date_string:
        return "Recently"
    
    try:
        # Handle ISO format with Z
        if 'Z' in date_string:
            date_obj = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        # Handle ISO format without Z
        elif 'T' in date_string:
            date_obj = datetime.fromisoformat(date_string)
        # Handle simple date format
        else:
            date_obj = datetime.strptime(date_string, "%Y-%m-%d")
            
        return date_obj.strftime("%B %d, %Y")
    except:
        return date_string

def ensure_valid_image_url(url):
    """Ensure the image URL is valid and has a proper protocol."""
    if not url:  # Handle None or empty string
        return 'https://via.placeholder.com/800x450/4f46e5/ffffff?text=AI+Newsroom'
        
    # Convert URL to string if it's another type
    url = str(url)
    
    # Fix URLs without protocol
    if url.startswith('//'):
        return f"https:{url}"
    
    # Ensure URL has a protocol
    if not url.startswith(('http://', 'https://')):
        return f"https://{url}"
        
    return url

# Add this route to handle default profile image
@app.route('/default.jpg')
def default_profile_image():
    # Redirect to a placeholder image service if default.jpg doesn't exist
    return redirect('https://via.placeholder.com/150x150/4f46e5/ffffff?text=User')

# Create a CLI command for database initialization
@app.cli.command("init-db")
def init_db_command():
    """Initialize the database."""
    db.create_all()
    print("Database tables created.")

# Function to ensure database is initialized when app starts
def init_app():
    # Create tables if they don't exist
    with app.app_context():
        db.create_all()

# Example admin route to add sample data for testing
@app.route('/admin/init-db')
def admin_init_db():
    if os.path.exists('instance/newsroom.db'):
        return "Database already exists. Not overwriting."
    
    with app.app_context():
        db.create_all()
        
        # Create demo user
        demo_user = User(
            username="demo",
            email="demo@example.com",
            full_name="Demo User"
        )
        demo_user.set_password("password")
        db.session.add(demo_user)
        db.session.flush()
        
        # Create preferences
        pref = UserPreference(user_id=demo_user.id)
        db.session.add(pref)
        
        # Create rewards
        reward = Reward(
            user_id=demo_user.id,
            points=250,
            level="News Explorer",
            streak_days=3,
            last_daily_points=datetime.now().date()  # Initialize to avoid None error
        )
        db.session.add(reward)
        
        # Add interests
        interests = ['Technology', 'Business', 'Science']
        for interest in interests:
            user_interest = UserInterest(user_id=demo_user.id, interest=interest)
            db.session.add(user_interest)
        
        db.session.commit()
        return "Database initialized with demo data!"

# Call the init function when the app starts
init_app()

if __name__ == '__main__':
    app.run(debug=True)
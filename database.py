from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import os
import logging
from dotenv import load_dotenv
import pymysql

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

# Database configuration for MySQL/XAMPP
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_root", "")  # Default XAMPP has no password
DB_NAME = os.getenv("DB_NAME", "phishguard")

# Construct database URL
if DB_PASSWORD:
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    DATABASE_URL = f"mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Override with direct URL from .env if provided
DATABASE_URL = os.getenv("DATABASE_URL", DATABASE_URL)

logger.info(f"Database URL: mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# Create engine with MySQL specific settings
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,   # Recycle connections every hour
    echo=False,          # Set to True for SQL debugging
    connect_args={
        "charset": "utf8mb4",
        "autocommit": False,
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
    }
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base
Base = declarative_base()

# Database dependency
def get_db():
    """Database dependency for FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_database():
    """Create database if it doesn't exist"""
    try:
        # Connect without specifying database to create it
        if DB_PASSWORD:
            temp_url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}"
        else:
            temp_url = f"mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}"
        
        temp_engine = create_engine(temp_url, echo=False)
        
        with temp_engine.connect() as conn:
            # Check if database exists
            result = conn.execute(text(f"SHOW DATABASES LIKE '{DB_NAME}'"))
            if not result.fetchone():
                # Create database if it doesn't exist
                conn.execute(text(f"CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                logger.info(f"✅ Database '{DB_NAME}' created successfully")
            else:
                logger.info(f"✅ Database '{DB_NAME}' already exists")
        
        temp_engine.dispose()
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creating database: {e}")
        return False

def create_tables():
    """Create all database tables"""
    try:
        # First ensure database exists
        create_database()
        
        # Import models after database creation
        from models import Base
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created successfully")
        
        # Log created tables
        with engine.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]
            if tables:
                logger.info(f"✅ Tables in database: {', '.join(tables)}")
            else:
                logger.warning("⚠️ No tables found in database")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creating tables: {e}")
        return False

def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            test_result = result.fetchone()
            if test_result and test_result[0] == 1:
                logger.info("✅ Database connection successful")
                
                # Test database selection
                conn.execute(text(f"USE {DB_NAME}"))
                logger.info(f"✅ Successfully connected to database '{DB_NAME}'")
                
                return True
            else:
                logger.error("❌ Database connection test failed")
                return False
                
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        logger.error("Please ensure:")
        logger.error("  1. XAMPP is running")
        logger.error("  2. MySQL service is started in XAMPP Control Panel")
        logger.error("  3. MySQL is running on port 3306")
        logger.error("  4. No firewall blocking the connection")
        return False

def get_database_info():
    """Get database information for debugging"""
    try:
        with engine.connect() as conn:
            # Get MySQL version
            version_result = conn.execute(text("SELECT VERSION()"))
            mysql_version = version_result.fetchone()[0]
            
            # Get current database
            db_result = conn.execute(text("SELECT DATABASE()"))
            current_db = db_result.fetchone()[0]
            
            # Get table count
            tables_result = conn.execute(text("SHOW TABLES"))
            table_count = len(tables_result.fetchall())
            
            info = {
                "mysql_version": mysql_version,
                "current_database": current_db,
                "table_count": table_count,
                "connection_url": f"mysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
            }
            
            return info
            
    except Exception as e:
        logger.error(f"❌ Error getting database info: {e}")
        return None

def reset_database():
    """Reset database by dropping and recreating all tables"""
    try:
        logger.warning("⚠️ Resetting database - all data will be lost!")
        
        # Import models
        from models import Base
        
        # Drop all tables
        Base.metadata.drop_all(bind=engine)
        logger.info("✅ All tables dropped")
        
        # Recreate all tables
        Base.metadata.create_all(bind=engine)
        logger.info("✅ All tables recreated")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error resetting database: {e}")
        return False

def backup_database(backup_file: str = None):
    """Create a backup of the database"""
    try:
        import subprocess
        from datetime import datetime
        
        if not backup_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"backup_phishguard_{timestamp}.sql"
        
        # Construct mysqldump command
        cmd = [
            "mysqldump",
            f"--host={DB_HOST}",
            f"--port={DB_PORT}",
            f"--user={DB_USER}",
        ]
        
        if DB_PASSWORD:
            cmd.append(f"--password={DB_PASSWORD}")
        
        cmd.extend([
            "--single-transaction",
            "--routines",
            "--triggers",
            DB_NAME
        ])
        
        # Execute backup
        with open(backup_file, 'w') as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ Database backup created: {backup_file}")
            return backup_file
        else:
            logger.error(f"❌ Backup failed: {result.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error creating backup: {e}")
        return None

def restore_database(backup_file: str):
    """Restore database from backup file"""
    try:
        import subprocess
        
        if not os.path.exists(backup_file):
            logger.error(f"❌ Backup file not found: {backup_file}")
            return False
        
        # Construct mysql command
        cmd = [
            "mysql",
            f"--host={DB_HOST}",
            f"--port={DB_PORT}",
            f"--user={DB_USER}",
        ]
        
        if DB_PASSWORD:
            cmd.append(f"--password={DB_PASSWORD}")
        
        cmd.append(DB_NAME)
        
        # Execute restore
        with open(backup_file, 'r') as f:
            result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ Database restored from: {backup_file}")
            return True
        else:
            logger.error(f"❌ Restore failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error restoring database: {e}")
        return False

def check_database_health():
    """Check database health and return status"""
    try:
        health_status = {
            "connection": False,
            "database_exists": False,
            "tables_exist": False,
            "demo_user_exists": False,
            "total_users": 0,
            "total_scans": 0,
            "last_error": None
        }
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            health_status["connection"] = True
            
            # Check if database exists
            result = conn.execute(text(f"SHOW DATABASES LIKE '{DB_NAME}'"))
            if result.fetchone():
                health_status["database_exists"] = True
                
                # Use the database
                conn.execute(text(f"USE {DB_NAME}"))
                
                # Check if tables exist
                tables_result = conn.execute(text("SHOW TABLES"))
                tables = [row[0] for row in tables_result.fetchall()]
                
                if 'users' in tables:
                    health_status["tables_exist"] = True
                    
                    # Count users
                    user_count_result = conn.execute(text("SELECT COUNT(*) FROM users"))
                    health_status["total_users"] = user_count_result.fetchone()[0]
                    
                    # Check demo user
                    demo_result = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'demo'"))
                    health_status["demo_user_exists"] = demo_result.fetchone()[0] > 0
                    
                    # Count scans if table exists
                    if 'scan_history' in tables:
                        scan_count_result = conn.execute(text("SELECT COUNT(*) FROM scan_history"))
                        health_status["total_scans"] = scan_count_result.fetchone()[0]
        
        return health_status
        
    except Exception as e:
        health_status["last_error"] = str(e)
        logger.error(f"❌ Database health check failed: {e}")
        return health_status

def initialize_database():
    """Initialize database with all required components"""
    try:
        logger.info("🚀 Initializing PhishGuard database...")
        
        # Step 1: Test connection
        if not test_connection():
            logger.error("❌ Database initialization failed: No connection")
            return False
        
        # Step 2: Create database if needed
        if not create_database():
            logger.error("❌ Database initialization failed: Cannot create database")
            return False
        
        # Step 3: Create tables
        if not create_tables():
            logger.error("❌ Database initialization failed: Cannot create tables")
            return False
        
        # Step 4: Check health
        health = check_database_health()
        if not health["connection"] or not health["database_exists"] or not health["tables_exist"]:
            logger.error("❌ Database initialization failed: Health check failed")
            return False
        
        logger.info("✅ Database initialization completed successfully")
        logger.info(f"✅ Database: {DB_NAME}")
        logger.info(f"✅ Tables: {health['tables_exist']}")
        logger.info(f"✅ Users: {health['total_users']}")
        logger.info(f"✅ Scans: {health['total_scans']}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False

# Auto-initialize on import for development
if __name__ != "__main__":
    try:
        # Only auto-initialize if we can connect
        test_connection()
    except:
        # If connection fails, log but don't raise error
        logger.warning("⚠️ Database not available during import")
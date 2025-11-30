import os
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime

# --- Configuração de Conexão (Compatível com Render) ---
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///idle_war.db")

# Correção para o prefixo do PostgreSQL no Render (postgres:// -> postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Modelos de Dados ---

class Player(Base):
    __tablename__ = "players"

    id = Column(BigInteger, primary_key=True, index=True) # ID do Telegram
    username = Column(String(50), nullable=True)
    name = Column(String(100))
    class_name = Column(String(20))
    
    # Progresso
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    gold = Column(Integer, default=0)
    gems = Column(Integer, default=0)
    current_phase_id = Column(Integer, default=1) # Começa na fase 1
    
    # Atributos de Batalha (Upgradáveis)
    health = Column(Integer)
    max_health = Column(Integer)
    strength = Column(Integer)
    intelligence = Column(Integer)
    defense = Column(Integer)
    speed = Column(Integer, default=5)
    crit_chance = Column(Integer, default=5)
    
    # Recursos
    stamina = Column(Integer, default=5)
    max_stamina = Column(Integer, default=5)
    
    # Social
    pvp_rating = Column(Integer, default=1000)
    guild_id = Column(Integer, ForeignKey("guilds.id"), nullable=True)
    
    # Timestamps
    last_daily_claim = Column(DateTime, default=datetime.min)
    last_stamina_gain = Column(DateTime, default=datetime.min)

class Guild(Base):
    __tablename__ = "guilds"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True)
    leader_id = Column(BigInteger)
    total_rating = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

# Função para criar tabelas
def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

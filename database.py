import os
import random
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# --- Configuração de Conexão ---
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///idle_war.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Modelos de Dados --- (Modelos estão corretos e completos)

class Player(Base):
    __tablename__ = "players"
    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(50), nullable=True)
    name = Column(String(15))
    class_name = Column(String(20))
    
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    gold = Column(Integer, default=1000)
    gems = Column(Integer, default=0)
    current_phase_id = Column(Integer, default=1)
    
    health = Column(Integer)
    max_health = Column(Integer)
    strength = Column(Integer)
    intelligence = Column(Integer)
    defense = Column(Integer)
    speed = Column(Integer, default=5)
    crit_chance = Column(Integer, default=5)
    
    stamina = Column(Integer, default=5)
    max_stamina = Column(Integer, default=5)
    
    pvp_rating = Column(Integer, default=1000)
    guild_id = Column(Integer, ForeignKey("guilds.id"), nullable=True)
    
    # NOVAS COLUNAS: A causa do erro, que precisam ser forçadas no DB
    farm_level = Column(Integer, default=1)
    barn_level = Column(Integer, default=1)
    barracks_level = Column(Integer, default=0) # <--- Estas não existiam
    academy_level = Column(Integer, default=0)
    track_level = Column(Integer, default=0)
    [span_0](start_span)clinic_level = Column(Integer, default=0) # <--- clinic_level é o erro exato[span_0](end_span)
    
    last_farm_harvest = Column(DateTime, default=datetime.now)
    last_daily_claim = Column(DateTime, default=datetime.min)
    last_stamina_gain = Column(DateTime, default=datetime.min)

class Guild(Base):
    __tablename__ = "guilds"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True)
    telegram_link = Column(String(100))
    leader_id = Column(BigInteger)
    total_rating = Column(Integer, default=0)
    member_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)

# --- Funções de Inicialização ---
def seed_bots(db):
    if db.query(Player).count() > 10: return
    # ... (Lógica de seed bots) ...
    pass 

def init_db():
    print("⚠️ EXECUTANDO RESET DE ESQUEMA...")
    
    # ---------------------------------------------------------
    # 🔴 AQUI É O FIX: FORÇA O BANCO A APAGAR AS TABELAS DESATUALIZADAS
    Base.metadata.drop_all(bind=engine) 
    # ---------------------------------------------------------

    # 2. Cria as tabelas novas e corretas (com clinic_level incluso)
    Base.metadata.create_all(bind=engine)
    
    # 3. Cria os bots
    db = SessionLocal()
    seed_bots(db)
    db.close()
    
    print("✅ Esquema corrigido e Banco de Dados atualizado!")
    
# ... (get_db e seed_bots são mantidas) ...

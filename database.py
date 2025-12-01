import os
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# --- Configuração de Conexão ---
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///idle_war.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Modelos de Dados ---

class Player(Base):
    __tablename__ = "players"

    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(50), nullable=True)
    name = Column(String(15))
    class_name = Column(String(20))
    
    # Economia
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    gold = Column(Integer, default=1000)
    gems = Column(Integer, default=0)
    current_phase_id = Column(Integer, default=1)
    
    # Atributos
    health = Column(Integer)
    max_health = Column(Integer)
    strength = Column(Integer)
    intelligence = Column(Integer)
    defense = Column(Integer)
    speed = Column(Integer, default=5)
    crit_chance = Column(Integer, default=5)
    
    stamina = Column(Integer, default=5)
    max_stamina = Column(Integer, default=5)
    
    # Construções
    armor_tier = Column(Integer, default=0)
    armor_level = Column(Integer, default=0)
    farm_level = Column(Integer, default=1)
    barn_level = Column(Integer, default=1)
    barracks_level = Column(Integer, default=0)
    academy_level = Column(Integer, default=0)
    track_level = Column(Integer, default=0)
    clinic_level = Column(Integer, default=0)

    # Social & Admin
    guild_id = Column(Integer, ForeignKey("guilds.id"), nullable=True)
    guild_role = Column(String(20), default="membro") # lider, coolider, anciao, membro
    guild_join_date = Column(DateTime, default=datetime.now) # Para antiguidade
    
    # Cooldowns de Guilda
    last_kick_action = Column(DateTime, default=datetime.min)
    last_guild_mail = Column(DateTime, default=datetime.min)

    referral_count = Column(Integer, default=0)
    referred_by = Column(BigInteger, nullable=True)
    is_banned = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    ban_reason = Column(String(100), nullable=True)
    
    # Competitivo
    pvp_rating = Column(Integer, default=1000)
    battles_won = Column(Integer, default=0)
    battles_lost = Column(Integer, default=0)
    daily_streak = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.now)
    last_active = Column(DateTime, default=datetime.now)
    last_farm_harvest = Column(DateTime, default=datetime.now)
    last_daily_claim = Column(DateTime, default=datetime.min)
    last_stamina_gain = Column(DateTime, default=datetime.min)

class Guild(Base):
    __tablename__ = "guilds"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True)
    description = Column(String(140), default="Bem-vindo à nossa guilda!")
    telegram_link = Column(String(100))
    leader_id = Column(BigInteger)
    is_private = Column(Boolean, default=False)
    
    # Progresso do Clã (Eras)
    level = Column(Integer, default=1)
    xp = Column(BigInteger, default=0)

    # Status
    total_rating = Column(Integer, default=0)
    member_count = Column(Integer, default=1)
    treasury_gold = Column(Integer, default=0)
    treasury_gems = Column(Integer, default=0)
    
    # Inatividade do Líder
    leadership_transfer_active = Column(Boolean, default=False)
    leadership_transfer_start = Column(DateTime, nullable=True)

    # Guerra (Futuro)
    war_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

class GuildRequest(Base):
    __tablename__ = "guild_requests"
    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(Integer, ForeignKey("guilds.id"))
    player_id = Column(BigInteger, ForeignKey("players.id"))
    created_at = Column(DateTime, default=datetime.now)

# --- Inicialização ---

def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Banco de Dados Carregado!")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# No final do arquivo database.py

def init_db():
    # --- PERIGO: A LINHA ABAIXO APAGA TUDO ---
    print("☢️ INICIANDO RESET TOTAL DO BANCO DE DADOS...")
    Base.metadata.drop_all(bind=engine)
    print("🗑️ Tabelas antigas removidas.")
    
    # --- RECRIANDO ---
    Base.metadata.create_all(bind=engine)
    print("✅ Novas tabelas criadas com sucesso (Versão Beta 2.0)!")

# (O resto do arquivo continua igual)


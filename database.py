import os
import random
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, ForeignKey, Boolean, text
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

    # Identificação
    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(50), nullable=True)
    name = Column(String(15))
    class_name = Column(String(20))
    
    # Progresso e Economia
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    gold = Column(Integer, default=1000)
    gems = Column(Integer, default=0)
    current_phase_id = Column(Integer, default=1)
    
    # Atributos de Batalha
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
    
    # Equipamento e Construções
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
    telegram_link = Column(String(100))
    leader_id = Column(BigInteger)
    total_rating = Column(Integer, default=0)
    member_count = Column(Integer, default=1)
    treasury_gold = Column(Integer, default=0)
    treasury_gems = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

# --- Migração e Inicialização ---

def seed_bots(db):
    """Cria bots escalonados até o Nível 666 para o Ranking"""
    if db.query(Player).count() > 10: return

    print("Criando bots Lendários para o Ranking...")
    prefixes = ["Dark", "Light", "Shadow", "Iron", "Gold", "Fire", "Ice", "Storm", "Elite", "Pro", "God", "Lord"]
    suffixes = ["Slayer", "King", "Wolf", "Bear", "Hawk", "Master", "Mage", "Knight", "Br", "X", "Soul", "Viper"]
    classes = ["Guerreiro", "Mago", "Arqueiro", "Paladino", "Ogro", "Necromante", "Assassino", "Feiticeiro"]
    
    bots = []
    
    # 1. O REI DO SERVIDOR (Top 1 - Nível 666)
    top1 = Player(
        id=666666, username="top1_king", name="DiabloPrime", class_name="Necromante",
        level=666, xp=0, gold=100000000, gems=66666,
        pvp_rating=5000,
        health=50000, max_health=50000, 
        strength=2000, intelligence=2000, defense=2000, 
        speed=100, crit_chance=50,
        battles_won=6666, battles_lost=0
    )
    bots.append(top1)

    # 2. A ELITE E A MASSA (199 Bots)
    for i in range(1, 200):
        if i < 5: lvl = random.randint(500, 600)   # Top 5
        elif i < 20: lvl = random.randint(300, 499) # Top 20
        elif i < 50: lvl = random.randint(100, 299) # Top 50
        else: lvl = random.randint(1, 99)           # Resto
        
        name = f"{random.choice(prefixes)}{random.choice(suffixes)}{random.randint(1, 99)}"[:15]
        
        # Escala de Atributos
        hp = 100 + (lvl * 50)
        stats = 10 + (lvl * 5)
        
        bot = Player(
            id=100000 + i, username=f"bot_{i}", name=name, class_name=random.choice(classes),
            level=lvl, xp=0, gold=random.randint(100, 50000) * lvl, gems=random.randint(0, 100),
            pvp_rating=1000 + (lvl * 15) + random.randint(-50, 50),
            health=hp, max_health=hp, 
            strength=stats, intelligence=stats, defense=stats, 
            speed=5 + int(lvl/20), crit_chance=5 + int(lvl/50),
            battles_won=random.randint(0, 50) + lvl, battles_lost=random.randint(0, 50)
        )
        bots.append(bot)
    
    db.add_all(bots)
    db.commit()
    print("Bots lendários criados!")

def init_db():
    # Cria tabelas se não existirem
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    seed_bots(db)
    db.close()
    
    print("✅ Banco de Dados Carregado!")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

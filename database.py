import os
import random
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# --- Configuração de Conexão (Compatível com Render) ---
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///idle_war.db")

# Correção obrigatória para o Render (postgres:// -> postgresql://)
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
    name = Column(String(15)) # Limite 15 chars
    class_name = Column(String(20))
    
    # Progresso Principal
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
    speed = Column(Integer, default=5)      # Velocidade/Iniciativa
    crit_chance = Column(Integer, default=5) # Chance Crítica (%)
    
    # Recursos de Energia
    stamina = Column(Integer, default=5)
    max_stamina = Column(Integer, default=5)
    
    # Social (Guilda e PvP)
    pvp_rating = Column(Integer, default=1000)
    guild_id = Column(Integer, ForeignKey("guilds.id"), nullable=True)
    
    # Sistema de Fazenda (Novos Campos)
    farm_level = Column(Integer, default=1)      # Nível da Plantação
    barn_level = Column(Integer, default=1)      # Nível do Celeiro
    last_farm_harvest = Column(DateTime, default=datetime.now) # Última colheita

    # Timestamps para Cooldowns
    last_daily_claim = Column(DateTime, default=datetime.min)
    last_stamina_gain = Column(DateTime, default=datetime.min)

class Guild(Base):
    __tablename__ = "guilds"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True)
    telegram_link = Column(String(100)) # Link do Grupo Telegram
    leader_id = Column(BigInteger)
    total_rating = Column(Integer, default=0)
    member_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)

# --- Funções de Inicialização e Bots ---

def seed_bots(db):
    """Cria 200 bots se o banco estiver vazio para popular o Ranking"""
    if db.query(Player).count() > 10:
        return # Já existem jogadores, não cria bots

    print("Populando Ranking com 200 Bots...")
    
    prefixes = ["Dark", "Light", "Shadow", "Iron", "Gold", "Fire", "Ice", "Storm", "Elite", "Pro"]
    suffixes = ["Slayer", "King", "Wolf", "Bear", "Hawk", "Lord", "Mage", "Knight", "Br", "X"]
    classes = ["Guerreiro", "Mago", "Arqueiro", "Paladino", "Ogro", "Necromante", "Assassino", "Feiticeiro"]
    
    bots = []
    for i in range(200):
        # Gera nome aleatório
        name = f"{random.choice(prefixes)}{random.choice(suffixes)}{random.randint(1, 99)}"
        name = name[:15] # Garante limite de caracteres
        
        char_class = random.choice(classes)
        lvl = random.randint(1, 50)
        
        # Cria o Bot com status variados
        bot = Player(
            id=100000 + i, # ID Falso
            username=f"bot_{i}",
            name=name,
            class_name=char_class,
            level=lvl,
            xp=0,
            gold=random.randint(100, 50000),
            gems=random.randint(0, 100),
            pvp_rating=1000 + (lvl * 10) + random.randint(-50, 50),
            # Status base genéricos para o bot
            health=100, max_health=100, strength=10, intelligence=10, defense=10,
            speed=5, crit_chance=5
        )
        bots.append(bot)
    
    db.add_all(bots)
    db.commit()
    print("Bots criados com sucesso!")

def init_db():
    """Inicializa o Banco de Dados"""
    
    # ---------------------------------------------------------
    # ⚠️ ÁREA DE RESET (Use apenas para corrigir o esquema)
    # Como você adicionou colunas novas (farm, guild link), 
    # precisamos apagar as tabelas antigas.
    # ---------------------------------------------------------
    print("♻️ RESETANDO TABELAS DO BANCO DE DADOS...")
    Base.metadata.drop_all(bind=engine) 
    # ---------------------------------------------------------

    # Cria as tabelas novas (Corretas)
    Base.metadata.create_all(bind=engine)
    
    # Cria os bots novamente
    db = SessionLocal()
    seed_bots(db)
    db.close()
    
    print("✅ Banco de Dados Atualizado e Pronto!")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

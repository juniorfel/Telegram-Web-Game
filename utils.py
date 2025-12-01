import random
from datetime import datetime, timedelta
from database import SessionLocal, Player
from config import ADMIN_ID

def get_db():
    return SessionLocal()

def get_player(user_id, db):
    return db.query(Player).filter(Player.id == user_id).first()

def format_number(num):
    return str(int(num)) if num else "0"

def is_admin(user_id, db=None):
    if user_id == ADMIN_ID: return True
    if db:
        p = get_player(user_id, db)
        if p and p.is_admin: return True
    return False

def check_level_up(player):
    leveled_up = False
    if not player.xp: player.xp = 0
    if not player.level: player.level = 1
    while player.xp >= player.level * 100:
        player.xp -= player.level * 100
        player.level += 1
        player.max_health += 5
        player.health = player.max_health 
        player.strength += 1
        player.defense += 1
        leveled_up = True
    return leveled_up

def generate_monster(phase_id):
    mult = 1.1 ** (phase_id - 1)
    is_boss = (phase_id % 10 == 0)
    name = f"Boss Fase {phase_id}" if is_boss else f"Monstro Fase {phase_id}"
    gold = 1000 * (2 ** ((phase_id-1)//10)) if is_boss else 100 * (2 ** ((phase_id-1)//10))
    xp = 50 * phase_id
    return {"name": name, "hp": int(30*mult), "atk": int(5*mult), "def": int(2*mult), "spd": int(4*mult), "gold": gold, "xp": xp, "is_boss": is_boss}

def apply_passive_healing(player, db):
    player.last_stamina_gain = datetime.now()
    return 0

# --- ESTATÍSTICAS TOTAIS (COM BÔNUS DE CARGO) ---
def get_total_stats(player):
    stats = {
        'str': player.strength, 'int': player.intelligence,
        'def': player.defense, 'spd': player.speed, 'hp': player.max_health
    }
    multiplier = 1.0
    if player.guild_id and player.guild_role:
        if player.guild_role == 'lider': multiplier = 1.10    # +10%
        elif player.guild_role == 'coolider': multiplier = 1.05 # +5%
        elif player.guild_role == 'anciao': multiplier = 1.02   # +2%
    
    final_stats = {k: int(v * multiplier) for k, v in stats.items()}
    final_stats['bonus_desc'] = f"+{int((multiplier-1)*100)}%" if multiplier > 1 else ""
    return final_stats

# --- SIMULAÇÃO PVP (COM STATS TOTAIS) ---
def simulate_pvp_battle(attacker, defender):
    s_atk = get_total_stats(attacker)
    s_def = get_total_stats(defender)
    
    hp_atk = s_atk['hp']
    hp_def = s_def['hp']
    atk_turn = s_atk['spd'] >= s_def['spd']
    
    for _ in range(20): # Max 20 turnos
        if hp_atk <= 0 or hp_def <= 0: break
        
        act = s_atk if atk_turn else s_def
        pas = s_def if atk_turn else s_atk
        act_obj = attacker if atk_turn else defender 
        
        if random.randint(1, 100) <= max(0, (pas['spd'] - act['spd']) * 2): # Dodge
            atk_turn = not atk_turn; continue

        dmg = (act['str'] * 2) + act['int']
        if random.randint(1, 100) <= act_obj.crit_chance: dmg *= 2
        
        reduction = pas['def'] / (pas['def'] + 100)
        dmg_final = int(dmg * (1 - reduction))
        
        if atk_turn: hp_def -= dmg_final
        else: hp_atk -= dmg_final
        atk_turn = not atk_turn

    return attacker if hp_atk > 0 else defender

# --- SISTEMA DE ERAS E NÍVEIS ---
def get_guild_level_data(level):
    eras = ["Idade da Pedra", "Idade da Madeira", "Idade do Bronze", 
            "Idade do Ferro", "Idade do Aço", "Era Feudal", 
            "Era Imperial", "Era Mística", "Era Dracônica", "Era Divina"]
    
    if level >= 30: return "Era Divina III", 0
    
    era_index = (level - 1) // 3
    era_name = eras[min(era_index, 9)]
    roman = "I" * ((level - 1) % 3 + 1)
    
    return f"{era_name} {roman}", int(5000 * (level ** 1.5))

def check_guild_level_up(guild):
    leveled_up = False
    while True:
        if guild.level >= 30: break
        _, xp_needed = get_guild_level_data(guild.level)
        if guild.xp >= xp_needed:
            guild.xp -= xp_needed
            guild.level += 1
            leveled_up = True
        else: break
    return leveled_up

# --- CÁLCULOS DE DIÁRIO ---

def calculate_daily_bonus(player, guild=None):
    """Versão simplificada antiga (mantida por segurança)"""
    gold, xp, gems, _, _ = calculate_daily_values(player, guild)
    bonus_msg = ""
    if guild:
        multiplier = 1 + (guild.level * 0.02)
        bonus_msg = f"\n🛡️ **Bônus de Clã:** +{int((multiplier-1)*100)}% Ouro/XP"
        if guild.level >= 10:
            gems_bonus = 2 + (guild.level - 10)
            bonus_msg += f"\n💎 **Bônus de Clã:** +{gems_bonus} Gemas!"
    return gold, xp, gems, bonus_msg

def calculate_daily_values(player, guild=None):
    """
    Calcula os valores do diário simulando a streak do dia.
    Retorna: gold, xp, gems, next_streak, is_double
    """
    # 1. Determinar Streak
    now = datetime.now()
    last = player.last_daily_claim
    
    # Se nunca pegou ou se passou mais de 48h, reseta para 1
    if last == datetime.min or (now - last).days > 1:
        next_streak = 1
    # Se pegou ontem (menos de 48h e dia diferente), aumenta
    elif (now - last).days == 1 or ((now - last).days == 0 and now.day != last.day):
        next_streak = player.daily_streak + 1
    else:
        # Se está tentando pegar de novo no mesmo dia, mantém o atual
        next_streak = player.daily_streak

    # 2. Valores Base
    gold = 1000
    xp = 1000
    gems = 5 # Fixo conforme pedido

    # 3. Bônus de Guilda (Passivo)
    if guild:
        multiplier = 1 + (guild.level * 0.02) # +2% por nivel
        gold = int(gold * multiplier)
        xp = int(xp * multiplier)
        # Gemas extras de guilda se Nvl >= 10
        if guild.level >= 10:
            gems += 2 + (guild.level - 10)

    # 4. Bônus de 7 Dias (DOBRO DE TUDO)
    is_double = (next_streak % 7 == 0) and next_streak > 0
    if is_double:
        gold *= 2
        xp *= 2
        gems *= 2
        
    return gold, xp, gems, next_streak, is_double

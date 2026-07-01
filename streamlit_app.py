import streamlit as st
import pandas as pd

# ==========================================
# 1. PAGE CONFIGURATION & SETUP
# ==========================================
st.set_page_config(page_title="Singapore Welfare Cliff Simulator", layout="wide")
st.title("Economic Welfare Simulator")
st.markdown("Modelling the change in expendable income as an effect of welfare policies")

# ==========================================
# 2. INPUT LEVERS & ARCHETYPES
# ==========================================
st.subheader("Household Parameters")

# Let the researcher toggle between the three specific demographic cliffs
archetype = st.radio("Select Household Archetype", [
    "Lower-Income Families (Triggers Childcare & SCFA)",
    "Seniors Age 65+ (Triggers Silver Support & CHAS)",
    "Single Adults (Triggers Public Rental Scheme)"
])

comcare_tier = st.selectbox(
    "Assumed ComCare SMTA Cash Payout (Based on latest MSF Data)",
    [
        "Median Payout ($380/month)",
        "75th Percentile Payout ($512/month)",
        "25th Percentile Payout ($250/month)"
    ]
)

selected_wage = st.slider("Gross Monthly Household Income ($)", min_value=0, max_value=5500, step=50, value=2150)

col_a, col_b = st.columns(2)
with col_a:
    household_size = st.slider("Household Size", min_value=1, max_value=6, step=1, value=3)
    has_newborn = st.checkbox("Household has a child aged 0–18 months", help="Adds the monthly equivalent of the Baby Bonus Cash Gift to net disposable income.")
with col_b:
    worker_age = st.slider("Worker Age", min_value=30, max_value=70, step=1, value=35)
    
st.subheader("Policy Interventions")
comcare_taper = st.slider(
    "ComCare Taper Rate (Benefit lost per extra dollar earned above $800 PCHI)", 
    min_value=0.0, max_value=1.0, step=0.05, value=0.30,
    help="0.0 means the benefit never decreases. 1.0 means a 1-to-1 strict cut. A traditional cliff is an instant drop to 0."
)

wis_cash_ratio = st.slider("WIS Liquid Cash Ratio", min_value=0.0, max_value=1.0, step=0.1, value=0.4, help="Adjusts how much of the WIS payout is given in liquid cash vs. CPF.")

st.divider()

# ==========================================
# 3. MATHEMATICAL ENGINE (POLICY CONSTANTS)
# ==========================================
def calculate_employee_cpf(gross_wage, age):
    """Calculates the employee CPF deduction."""
    if age <= 55: rate = 0.20
    elif 55 < age <= 60: rate = 0.17  
    elif 60 < age <= 65: rate = 0.115
    else: rate = 0.075 
    
    if 500 < gross_wage < 750: 
        phase_in_factor = (gross_wage - 500) / 250
        return gross_wage * rate * phase_in_factor
    else: 
        return gross_wage * rate
        
def calculate_wis_cash(gross_wage, age, wis_cash_ratio):
    """Calculates the liquid cash portion of WIS, featuring dynamic age tiers and an adjustable cash ratio."""
    # 1. Eligibility Check
    if not (500 <= gross_wage <= 3000) or age < 30: 
        return 0.0
    
    # 2. Dynamic Age Tiers (2025/2026 Parameters)
    if 30 <= age <= 34: max_annual_wis = 2450
    elif 35 <= age <= 44: max_annual_wis = 3500
    elif 45 <= age <= 59: max_annual_wis = 4200
    else: max_annual_wis = 4900
        
    # 3. The Liquidity Inversion 
    max_monthly_cash = (max_annual_wis / 12) * wis_cash_ratio
    
    # 4. The WIS Bell Curve
    if 500 <= gross_wage < 1200: 
        return max_monthly_cash * ((gross_wage - 500) / (1200 - 500))
    elif 1200 <= gross_wage <= 1500: 
        return max_monthly_cash
    elif 1500 < gross_wage <= 3000: 
        return max_monthly_cash * ((3000 - gross_wage) / (3000 - 1500))
    
    return 0.00

def calculate_baby_bonus_monthly(has_newborn):
    """Calculates the monthly tangible cash equivalent of the Baby Bonus."""
    if not has_newborn: return 0.0
    return 611.11

def calculate_comcare(gross_wage, household_size, comcare_tier, taper_rate):
    """Calculates ComCare SMTA with a dynamic tapering effect."""
    pchi = gross_wage / household_size
    
    if "Median" in comcare_tier: base_payout = 380.00
    elif "75th" in comcare_tier: base_payout = 512.00
    else: base_payout = 250.00

    if pchi <= 800: 
        return base_payout
        
    excess_income = gross_wage - (800 * household_size)
    benefit_reduction = excess_income * taper_rate
    return max(0.0, base_payout - benefit_reduction)

def calculate_ecda_out_of_pocket(gross_wage, num_young_children=1):
    if gross_wage <= 3000: net_fee = 3.00
    elif 3000 < gross_wage <= 4500: net_fee = 25.00
    elif 4500 < gross_wage <= 6000: net_fee = 115.00
    else: net_fee = 310.00
    return net_fee * num_young_children

def calculate_student_care_out_of_pocket(gross_wage, household_size, num_older_children=1):
    pchi = gross_wage / household_size
    base_fee = 300.00
    if pchi <= 375: subsidy = min(base_fee * 0.98, 290.00)
    elif 375 < pchi <= 500: subsidy = min(base_fee * 0.95, 280.00)
    elif 500 < pchi <= 550: subsidy = min(base_fee * 0.90, 266.00)
    else: subsidy = 0.00
    return (base_fee - subsidy) * num_older_children

def calculate_silver_support(gross_wage, household_size, age):
    if age < 65: return 0.0
    pchi = gross_wage / household_size
    if pchi <= 1500: return 1080.00 / 3
    elif 1500 < pchi <= 2300: return 540.00 / 3
    else: return 0.0

def calculate_senior_medical_costs(gross_wage, household_size, age):
    if age < 65: return 0.0
    pchi = gross_wage / household_size
    total_medical_need = 150.00 
    if pchi <= 1500: return total_medical_need - 41.00 
    elif 1500 < pchi <= 2300: return total_medical_need - 26.00
    else: return total_medical_need

def calculate_public_rental_cost(gross_wage):
    if gross_wage <= 800: return 33.00
    elif 800 < gross_wage <= 1500: return 90.00
    else: return 500.00

def calculate_net_cash(gross_wage, household_size, age, archetype, comcare_tier, taper_rate, has_newborn, wis_cash_ratio):
    """The dynamic Master Engine mapping the Bundle Collapse."""
    cpf_deduction = calculate_employee_cpf(gross_wage, age)
    wis_cash = calculate_wis_cash(gross_wage, age, wis_cash_ratio) 
    comcare = calculate_comcare(gross_wage, household_size, comcare_tier, taper_rate)
    baby_bonus = calculate_baby_bonus_monthly(has_newborn)
    
    work_expenses = 200 if gross_wage > 0 else 0 
    take_home = (gross_wage - cpf_deduction) + wis_cash + comcare + baby_bonus - work_expenses
    
    if "Families" in archetype:
        return take_home - calculate_ecda_out_of_pocket(gross_wage) - calculate_student_care_out_of_pocket(gross_wage, household_size)
    elif "Seniors" in archetype:
        return take_home + calculate_silver_support(gross_wage, household_size, age) - calculate_senior_medical_costs(gross_wage, household_size, age)
    else:
        return take_home - calculate_public_rental_cost(gross_wage)

def calculate_emtr(gross_wage, household_size, age, archetype, comcare_tier, taper_rate, has_newborn, wis_cash_ratio, step=100):
    if gross_wage == 0: return 0.0
    net_current = calculate_net_cash(gross_wage, household_size, age, archetype, comcare_tier, taper_rate, has_newborn, wis_cash_ratio)
    net_simulated = calculate_net_cash(gross_wage + step, household_size, age, archetype, comcare_tier, taper_rate, has_newborn, wis_cash_ratio)
    
    delta_gross = step
    delta_net = net_simulated - net_current
    return 1.0 - (delta_net / delta_gross)

def calculate_wdr(gross_wage, household_size, age, archetype, comcare_tier, taper_rate, has_newborn, wis_cash_ratio, step=100):
    if gross_wage == 0: return 0.0
    
    def get_components(wage):
        cpf = calculate_employee_cpf(wage, age)
        wis = calculate_wis_cash(wage, age, wis_cash_ratio)
        comcare = calculate_comcare(wage, household_size, comcare_tier, taper_rate)
        
        if "Families" in archetype:
            care = calculate_ecda_out_of_pocket(wage) + calculate_student_care_out_of_pocket(wage, household_size)
        elif "Seniors" in archetype:
            care = calculate_senior_medical_costs(wage, household_size, age)
        else:
            care = calculate_public_rental_cost(wage)
        return cpf, wis, comcare, care

    c1, w1, cc1, care1 = get_components(gross_wage)
    c2, w2, cc2, care2 = get_components(gross_wage + step)
    
    delta_wdr = (c2 - c1) + (care2 - care1) - (w2 - w1) + (cc1 - cc2)
    return delta_wdr / step

# ==========================================
# 4. DATA GENERATION (BUILDING THE CURVE)
# ==========================================
wage_range = list(range(0, 5550, 50)) 
data = []
mis_baseline = 1680 * household_size 

for w in wage_range:
    net = calculate_net_cash(w, household_size, worker_age, archetype, comcare_tier, comcare_taper, has_newborn, wis_cash_ratio)
    data.append({
        "Gross Wage": w, 
        "Net Disposable Cash": net,
        "MIS Basic Cost of Living": mis_baseline
    })

df = pd.DataFrame(data)

# Process current metrics ONCE
current_net_cash = calculate_net_cash(selected_wage, household_size, worker_age, archetype, comcare_tier, comcare_taper, has_newborn, wis_cash_ratio)
current_emtr = calculate_emtr(selected_wage, household_size, worker_age, archetype, comcare_tier, comcare_taper, has_newborn, wis_cash_ratio, step=100)
current_wdr = calculate_wdr(selected_wage, household_size, worker_age, archetype, comcare_tier, comcare_taper, has_newborn, wis_cash_ratio, step=100)

emtr_percentage = current_emtr * 100 
wdr_percentage = current_wdr * 100

# ==========================================
# 5. SINGLE, CLEAN UI LAYOUT
# ==========================================
col1, col2, col3, col4 = st.columns(4)
col1.metric(label="Selected Gross Wage", value=f"${selected_wage:,.2f}")
col2.metric(label="Net Disposable Cash", value=f"${current_net_cash:,.2f}")
col4.metric(label="Welfare Dependence Rate", value=f"{wdr_percentage:.1f}%")

if emtr_percentage >= 100:
    col3.metric(label="Marginal Tax Rate (EMTR)", value=f"{emtr_percentage:.1f}%", delta="CRITICAL CLIFF", delta_color="inverse")
elif emtr_percentage >= 70:
    col3.metric(label="Marginal Tax Rate (EMTR)", value=f"{emtr_percentage:.1f}%", delta="High Disincentive", delta_color="inverse")
else:
    col3.metric(label="Marginal Tax Rate (EMTR)", value=f"{emtr_percentage:.1f}%", delta="Healthy", delta_color="normal")

st.divider()

# The Main Visualizer
st.subheader("The Welfare Cliff Visualizer")
st.markdown("The chart maps Net Cash against Gross Wages. A sharp downward drop indicates the cliff where specific safety nets are withdrawn.")
st.line_chart(df.set_index("Gross Wage"))

# Deep Dive Data
tab1, tab2 = st.tabs(["Policy Breakdown", "Raw Data Engine"])
with tab1:
    st.write(f"### Financial Baseline at ${selected_wage} Gross Wage")
    st.write(f"* **Employee CPF Deduction:** -${calculate_employee_cpf(selected_wage, worker_age):.2f}")
    st.write(f"* **WIS Cash Received:** +${calculate_wis_cash(selected_wage, worker_age, wis_cash_ratio):.2f}")
    st.write(f"* **ComCare Received:** +${calculate_comcare(selected_wage, household_size, comcare_tier, comcare_taper):.2f}")
    if has_newborn:
        st.write(f"* **Baby Bonus Cash Received:** +${calculate_baby_bonus_monthly(has_newborn):.2f}")
    
with tab2:
    st.write("Complete underlying dataset for all wage intervals.")
    st.dataframe(df)
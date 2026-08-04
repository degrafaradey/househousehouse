"""
Доктор Хаус: Экономическое отделение
Мини-игра на базе DeepSeek API + Streamlit
"""

import streamlit as st
import requests
import json
import re

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

CHARACTERS = {
    "forman": {"name": "Форман", "color": "#D85A30", "bg": "#FAECE7"},
    "cameron": {"name": "Кэмерон", "color": "#1D9E75", "bg": "#E1F5EE"},
    "chase": {"name": "Чейз", "color": "#378ADD", "bg": "#E6F1FB"},
}

SYSTEM_PROMPT_MAIN = """Давай сыграем в игру. Ты — ведущий-нарратор в мире, где экономики — это
пациенты, а я — доктор-диагност вроде Грегори Хауса. Твоя команда — три экономических
консультанта: Форман (интервенционист, за прямое вмешательство государства), Кэмерон
(этик, думает о людях и социальных последствиях), Чейз (либерал/ортодокс, за рыночные
механизмы и осторожность с вмешательством).

Твои функции как ведущего:
1. Создать кейс: придумай "страну-пациента" со сложной экономической болезнью. Держи истинный
   диагноз в секрете до самого конца.
2. Выдать вводные: карточка пациента с цифрами (ВВП, инфляция, безработица, курс) и жалобами.
3. Реагировать на "тесты" и "лечение": игрок запрашивает статистику или предлагает меры
   политики — описывай реакцию экономики, которая может быть неожиданной.
4. Team-реакции: после каждого хода игрока три консультанта кратко реагируют на его мысль —
   каждый со своей позиции. КАЖДАЯ реплика персонажа — строго 2-4 предложения, без длинных
   монологов, без вводных фраз, сразу суть мнения.
5. В конце, когда игрок формулирует финальный диагноз — раскрой истинный диагноз и разбери
   кейс с точки зрения экономической теории.

ФОРМАТ ОТВЕТА — строго валидный JSON, без markdown-разметки, без ```json оберток, только сам
объект:
{
  "narrator": "текст ведущего: карточка пациента, результаты анализов, реакция экономики и т.д.",
  "reactions": [
    {"speaker": "forman", "text": "реплика Формана, 2-4 предложения"},
    {"speaker": "cameron", "text": "реплика Кэмерон, 2-4 предложения"},
    {"speaker": "chase", "text": "реплика Чейза, 2-4 предложения"}
  ]
}

Если это самый первый ход игры (карточка пациента) — reactions может быть пустым списком [].
Отвечай только на русском языке. Начни с первого кейса прямо сейчас, сделай его сложным, где
причины и следствия перепутаны."""

PERSONA_REACTION_PROMPT = """Ты играешь роль {name} в игре "Доктор Хаус: Экономическое
отделение". {persona_desc}

Тебе показывают последнее сообщение игрока (доктора-диагноста) в контексте текущего
экономического кейса. Отреагируй ТОЛЬКО от своего лица, 2-4 предложения, без вступлений вроде
"как {name}, я думаю". Сразу суть. Не используй JSON — просто обычный текст реплики.
Отвечай на русском языке."""

PERSONA_DESCRIPTIONS = {
    "forman": "Ты интервенционист — всегда предлагаешь прямое вмешательство государства, "
              "веришь в активную политику и не боишься смелых мер.",
    "cameron": "Ты этик — тебя в первую очередь волнуют люди и социальные последствия решений, "
               "а не только цифры.",
    "chase": "Ты рыночный либерал/ортодокс — скептичен к вмешательству государства, ценишь "
             "осторожность, любишь проверять цифры и риски.",
}

# ---------------------------------------------------------------------------
# Вызовы DeepSeek API
# ---------------------------------------------------------------------------

def call_deepseek(api_key: str, messages: list[dict], model: str, max_tokens: int = 1200) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.9,
        "max_tokens": max_tokens,
    }
    response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_main_response(raw: str) -> dict:
    """Достаём JSON из ответа модели, даже если она обернула его в ```json ... ```."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^```json\s*|^```\s*|```$", "", cleaned, flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
        if "narrator" not in data:
            data["narrator"] = raw
        if "reactions" not in data:
            data["reactions"] = []
        return data
    except json.JSONDecodeError:
        # Модель не выдала валидный JSON — показываем как есть, без реакций команды
        return {"narrator": raw, "reactions": []}


def get_persona_reaction(api_key: str, model: str, persona_key: str, history: list[dict],
                          last_user_message: str) -> str:
    persona = CHARACTERS[persona_key]
    system = PERSONA_REACTION_PROMPT.format(
        name=persona["name"], persona_desc=PERSONA_DESCRIPTIONS[persona_key]
    )
    context_snippets = []
    for m in history[-6:]:
        if m["role"] == "user":
            context_snippets.append(f"Доктор: {m['content']}")
        elif m["role"] == "assistant":
            context_snippets.append(f"[Ход игры]: {m['content'][:400]}")
    context_text = "\n".join(context_snippets)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Контекст последних ходов:\n{context_text}\n\n"
                                     f"Последнее сообщение доктора: {last_user_message}\n\n"
                                     f"Отреагируй."},
    ]
    return call_deepseek(api_key, messages, model, max_tokens=200)


# ---------------------------------------------------------------------------
# Рендер персонажа
# ---------------------------------------------------------------------------

def render_reaction(persona_key: str, text: str):
    p = CHARACTERS[persona_key]
    st.markdown(
        f"""<div style="display:flex;gap:10px;margin-bottom:10px;">
        <div style="width:32px;height:32px;border-radius:50%;background:{p['bg']};
        display:flex;align-items:center;justify-content:center;font-size:12px;
        font-weight:600;color:{p['color']};flex-shrink:0;">{p['name'][0]}</div>
        <div style="flex:1;background:{p['bg']}55;border-left:3px solid {p['color']};
        border-radius:0 8px 8px 0;padding:8px 12px;">
        <p style="font-size:12px;font-weight:600;color:{p['color']};margin:0 0 4px;">{p['name']}</p>
        <p style="font-size:14px;color:inherit;margin:0;line-height:1.5;">{text}</p>
        </div></div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Доктор Хаус: Экономическое отделение", page_icon="🩺")
st.title("🩺 Доктор Хаус: Экономическое отделение")
st.caption("Диагностируй больную экономику. Опрашивай агентов, назначай 'анализы', ищи диагноз.")

with st.sidebar:
    st.header("Настройки")
    api_key = st.text_input("DeepSeek API ключ", type="password", help="Формат sk-...")
    model_choice = st.selectbox("Модель", options=["deepseek-chat", "deepseek-reasoner"])

    st.divider()
    if st.button("🔄 Новый кейс (сбросить игру)"):
        st.session_state.messages = []
        st.session_state.persona_reactions = {}
        st.rerun()

    st.divider()
    st.markdown(
        "**Как получить ключ:**\n"
        "1. platform.deepseek.com → регистрация\n"
        "2. API Keys → Create new key\n"
        "3. Новым аккаунтам дают бесплатный грант токенов"
    )

if "messages" not in st.session_state:
    st.session_state.messages = []
if "persona_reactions" not in st.session_state:
    st.session_state.persona_reactions = {}  # {index_in_history: {persona: text}}

# ---------------------------------------------------------------------------
# История игры
# ---------------------------------------------------------------------------

for idx, msg in enumerate(st.session_state.messages):
    if msg["role"] == "system":
        continue
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(msg["content"])
    elif msg["role"] == "assistant":
        with st.chat_message("assistant"):
            data = parse_main_response(msg["content"])
            st.markdown(data["narrator"])
            for r in data["reactions"]:
                if r["speaker"] in CHARACTERS:
                    render_reaction(r["speaker"], r["text"])

            cols = st.columns(3)
            for i, key in enumerate(CHARACTERS):
                p = CHARACTERS[key]
                if cols[i].button(p["name"], key=f"btn_{idx}_{key}"):
                    if not api_key:
                        st.warning("Сначала введи API-ключ в панели слева.")
                    else:
                        with st.spinner(f"{p['name']} думает..."):
                            last_user = next(
                                (m["content"] for m in reversed(st.session_state.messages[:idx + 1])
                                 if m["role"] == "user"), ""
                            )
                            reaction = get_persona_reaction(
                                api_key, model_choice, key, st.session_state.messages, last_user
                            )
                            st.session_state.persona_reactions.setdefault(idx, {})[key] = reaction
                            st.rerun()

            if idx in st.session_state.persona_reactions:
                st.markdown("—")
                for key, text in st.session_state.persona_reactions[idx].items():
                    render_reaction(key, text)

# ---------------------------------------------------------------------------
# Старт игры
# ---------------------------------------------------------------------------

if not st.session_state.messages:
    if not api_key:
        st.info("Введи API-ключ DeepSeek в панели слева, чтобы начать игру.")
    else:
        with st.chat_message("assistant"):
            with st.spinner("Готовим первого пациента..."):
                try:
                    st.session_state.messages.append({"role": "system", "content": SYSTEM_PROMPT_MAIN})
                    reply = call_deepseek(api_key, st.session_state.messages, model_choice)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    st.rerun()
                except requests.exceptions.HTTPError as e:
                    st.error(f"Ошибка API: {e}")
                except Exception as e:
                    st.error(f"Что-то пошло не так: {e}")

# ---------------------------------------------------------------------------
# Ввод игрока
# ---------------------------------------------------------------------------

if api_key and st.session_state.messages:
    user_input = st.chat_input("Твой ход (вопрос, гипотеза, назначение анализа...)")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.spinner("Экономика реагирует..."):
            try:
                reply = call_deepseek(api_key, st.session_state.messages, model_choice)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                st.rerun()
            except requests.exceptions.HTTPError as e:
                st.error(f"Ошибка API: {e}")
            except Exception as e:
                st.error(f"Что-то пошло не так: {e}")

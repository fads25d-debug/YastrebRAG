"""Offline visual language for the Streamlit interface."""
import html

import streamlit as st


WING = '''<svg viewBox="0 0 48 48" fill="none" aria-hidden="true"><path d="M7 10L42 18L24 25L18 39L15 23L7 10Z" fill="currentColor"/><path d="M15 23L34 18L24 25" stroke="var(--brand-cut,#10283e)" stroke-width="2" stroke-linejoin="round"/></svg>'''


def brand():
    st.markdown(f'<div class="brand"><span class="brand-mark">{WING}</span>'
                '<div><strong>Ястреб</strong><span>Работа со знанием</span></div></div>', unsafe_allow_html=True)


def account(name, role):
    initials = ''.join(part[0] for part in name.split()[:2]).upper() or 'Я'
    st.markdown(f'<div class="account-identity"><span class="account-avatar">{html.escape(initials)}</span>'
                f'<div><strong>{html.escape(name)}</strong><span>{html.escape(role)}</span></div></div>',
                unsafe_allow_html=True)


def apply_theme(theme='Синяя', large=False):
    palettes = {
        'Синяя': ('#f7f9fb', '#ffffff', '#172c40', '#61758a', '#dfe6ed', '#214e73', '#10283e', '#eaf1f7', '#9eafbf', '#244158'),
        'Светлая': ('#fafbfc', '#ffffff', '#243340', '#657887', '#dee5eb', '#375973', '#edf1f4', '#233b4e', '#5f7486', '#dce5ec'),
        'Тёмная': ('#111c28', '#192735', '#e5edf5', '#a2b2c2', '#304253', '#9ac5e0', '#0b1723', '#e5edf5', '#a2b2c2', '#233d52'),
    }
    bg, surface, ink, muted, line, accent, side, side_ink, side_muted, selected = palettes.get(theme, palettes['Синяя'])
    st.markdown(f'''<style>
:root {{--bg:{bg};--surface:{surface};--ink:{ink};--muted:{muted};--line:{line};--accent:{accent};--side:{side};--side-ink:{side_ink};--side-muted:{side_muted};--selected:{selected};--brand-cut:{side};--body-size:{'18px' if large else '15px'};}}
.stApp,[data-testid="stMain"],[data-testid="stBottom"]>div {{background:var(--bg);color:var(--ink);}}
html,body,[data-testid="stApp"],button,input,textarea,select {{font-family:"Segoe UI Variable","Segoe UI","DejaVu Sans",sans-serif;}}
[data-testid="stMarkdownContainer"],.stApp label,.stApp [data-testid="stText"] {{color:var(--ink);}}
[data-testid="stCaptionContainer"] p {{color:var(--muted)!important;font-size:12px;line-height:1.65;}}
.stMainBlockContainer {{max-width:1030px;padding:2.4rem 3rem 2rem;}}
h1,h2,h3 {{color:var(--ink);font-family:inherit;}}
h1 {{font-size:clamp(29px,3.1vw,42px)!important;font-weight:600!important;letter-spacing:-1.5px;line-height:1.18!important;padding:0!important;}}
h2,h3 {{letter-spacing:-.45px;}}
[data-testid="stHeader"] {{background:transparent;}}
[data-testid="stExpandSidebarButton"] span {{color:var(--muted)!important;}}
.stAppDeployButton {{display:none;}}
.stApp button {{border-radius:9px;font-weight:500;transition:background .15s,border-color .15s;}}
.stApp button:focus-visible,.stApp input:focus-visible,.stApp textarea:focus-visible {{outline:3px solid #75abd0!important;outline-offset:3px;}}
.stApp button[kind="secondary"] {{background:var(--surface);border:1px solid var(--line);color:var(--ink);}}
.stApp button[kind="secondary"]:hover {{border-color:var(--accent);color:var(--accent);}}
.stApp button[kind="primary"] {{background:var(--accent);border:1px solid var(--accent);color:{'#132738' if theme == 'Тёмная' else '#ffffff'};}}
.stApp [data-baseweb="input"],.stApp [data-baseweb="select"]>div {{background:var(--surface);border-color:var(--line);color:var(--ink);border-radius:8px;}}
[data-testid="stSelectbox"] [role="group"],[data-testid="stTextInput"] input {{background:var(--surface);border-color:var(--line);color:var(--ink);border-radius:8px;}}
[data-testid="stSelectbox"] button {{color:var(--ink);}}
[role="listbox"] {{background:var(--surface);color:var(--ink);}}
[role="option"] {{color:var(--ink);}}
[role="option"][data-focused="true"] {{background:var(--line);}}
.stApp input,.stApp textarea {{color:var(--ink)!important;caret-color:var(--accent);}}
.stApp input::placeholder,.stApp textarea::placeholder {{color:var(--muted)!important;opacity:1;}}
[data-testid="stSidebar"] {{background:var(--side);color:var(--side-ink);min-width:294px;max-width:310px;border-right:1px solid var(--line);}}
[data-testid="stSidebarUserContent"] {{position:relative;min-height:calc(100dvh - 6rem);padding:0 22px 108px!important;}}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"], [data-testid="stSidebar"] [data-testid="stText"] {{color:var(--side-ink);}}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{color:var(--side-muted)!important;}}
[data-testid="stSidebar"] button[kind="headerNoPadding"] span {{color:var(--side-muted)!important;}}
.brand {{display:flex;align-items:center;gap:11px;padding:6px 0 28px;}}
.brand-mark {{width:41px;height:41px;display:grid;place-items:center;color:var(--side-ink);}}
.brand-mark svg {{width:39px;height:39px;}}
.brand strong {{font-size:25px;font-weight:650;letter-spacing:-.8px;line-height:1.3;}}
.brand>div>span {{display:block;font-size:11px;letter-spacing:.15px;color:var(--side-muted);margin-top:2px;}}
.st-key-new_dialog button {{background:var(--selected)!important;border:1px solid color-mix(in srgb,var(--side-ink) 18%,transparent)!important;color:var(--side-ink)!important;min-height:43px;margin-bottom:15px;}}
.st-key-new_dialog button:hover {{border-color:var(--side-ink)!important;}}
.st-key-history {{max-height:calc(100dvh - 300px);min-height:160px;overflow:auto;scrollbar-width:thin;scrollbar-color:var(--side-muted) transparent;}}
.st-key-history [data-testid="stVerticalBlock"] {{gap:5px;}}
.st-key-history button {{background:transparent!important;color:var(--side-muted)!important;border:1px solid transparent!important;min-height:42px;text-align:left;justify-content:flex-start;padding:9px 12px;}}
.st-key-history button p {{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px;}}
.st-key-history button[kind="primary"] {{background:var(--selected)!important;color:var(--side-ink)!important;box-shadow:inset 2px 0 0 #8bb7d4;}}
.st-key-history button:hover {{background:var(--selected)!important;color:var(--side-ink)!important;}}
.st-key-history [data-testid="stHorizontalBlock"] {{flex-wrap:nowrap!important;gap:4px;}}
.st-key-history [data-testid="stColumn"]:first-child {{flex:1 1 0!important;min-width:0!important;}}
.st-key-history [data-testid="stColumn"]:last-child {{flex:0 0 34px!important;min-width:34px!important;}}
.st-key-history [data-testid="stColumn"]:last-child button {{padding:6px;justify-content:center;}}
.st-key-history [data-testid="stColumn"]:last-child button p {{font-size:0;}}
.st-key-history [data-testid="stColumn"]:last-child button span {{color:var(--side-muted);}}
.st-key-history [data-testid="stColumn"]:last-child button:hover span {{color:#e89c9c;}}
.st-key-delete_confirmation [data-testid="stText"] span {{color:var(--side-ink);font-size:13px;}}
.st-key-account {{position:absolute;bottom:0;left:0;right:0;width:auto!important;border-top:1px solid color-mix(in srgb,var(--side-ink) 15%,transparent);padding:20px 0 4px;}}
.st-key-account [data-testid="stHorizontalBlock"] {{flex-wrap:nowrap!important;gap:8px;}}
.st-key-account [data-testid="stColumn"]:first-child {{flex:1 1 0!important;width:auto!important;min-width:0!important;}}
.st-key-account [data-testid="stColumn"]:last-child {{flex:0 0 38px!important;width:38px!important;min-width:38px!important;}}
.account-identity {{display:flex;gap:11px;align-items:center;min-width:0;}}
.account-avatar {{display:grid;place-items:center;flex:0 0 35px;height:35px;border:1px solid color-mix(in srgb,var(--side-ink) 22%,transparent);border-radius:50%;color:var(--side-ink);font-size:11px;}}
.account-identity>div {{min-width:0;}}
.account-identity strong {{display:block;color:var(--side-ink);font-size:13px;font-weight:550;overflow:hidden;text-overflow:ellipsis;}}
.account-identity span:not(.account-avatar) {{display:block;color:var(--side-muted);font-size:11px;margin-top:3px;}}
.st-key-account button {{background:transparent!important;color:var(--side-ink)!important;border:0!important;min-height:36px;font-size:21px;}}
.st-key-settings {{position:absolute;bottom:88px;left:0;right:0;width:100%;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:14px;padding:14px;z-index:40;box-shadow:0 -12px 40px #00102130;max-height:calc(100dvh - 160px);overflow:auto;}}
[data-testid="stSidebar"] .st-key-settings [data-testid="stMarkdownContainer"], [data-testid="stSidebar"] .st-key-settings [data-testid="stText"], .st-key-settings label {{color:var(--ink);}}
[data-testid="stSidebar"] .st-key-settings [data-testid="stCaptionContainer"] p {{color:var(--muted)!important;}}
.st-key-settings [data-baseweb="tab-list"] {{gap:13px;}}
.st-key-settings button[data-baseweb="tab"] {{font-size:11px;padding-left:0;padding-right:0;color:var(--muted);}}
.st-key-settings [role="tab"] {{font-size:11px;padding-left:0;padding-right:0;color:var(--muted);}}
.st-key-settings [role="tab"] p {{font-size:11px!important;white-space:nowrap;}}
.st-key-settings [role="tablist"] {{gap:8px;}}
.st-key-settings button[data-baseweb="tab"][aria-selected="true"] {{color:var(--accent);}}
.st-key-settings [data-testid="stFileUploaderDropzone"] {{background:var(--bg);padding:12px;}}
.workspace-bar {{display:flex;align-items:center;justify-content:space-between;gap:15px;border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:30px;font-size:12px;color:var(--muted);}}
.workspace-label {{font-weight:550;color:var(--ink);}}
.local-badge {{display:flex;align-items:center;gap:7px;white-space:nowrap;}}
.local-badge i {{width:6px;height:6px;border-radius:50%;background:#5a958b;}}
.intro-copy {{color:var(--muted);max-width:600px;font-size:16px;line-height:1.75;margin:15px 0 24px;}}
.st-key-mode {{margin:7px 0 12px;}}
.st-key-mode [role="radiogroup"] {{display:inline-flex;gap:3px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:4px;}}
.st-key-mode [data-testid="stRadioOption"] {{margin:0;padding:8px 17px;border-radius:7px;}}
.st-key-mode [data-testid="stRadioOption"]>div>div>div:first-child {{display:none;}}
.st-key-mode label:has(input:checked) {{background:var(--accent);}}
.st-key-mode label:has(input:checked) p {{color:{'#132738' if theme == 'Тёмная' else '#ffffff'}!important;}}
.st-key-mode label p {{font-size:13px;font-weight:550;}}
.st-key-mode label:focus-within {{outline:2px solid #75abd0;outline-offset:2px;}}
.empty-state {{padding:36px 0 25px;border-top:1px solid var(--line);margin-top:22px;}}
.empty-state h2 {{font-size:21px;font-weight:550;margin:0 0 12px;}}
.empty-state>p {{font-size:14px;color:var(--muted);line-height:1.8;max-width:590px;}}
.question-examples {{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:26px;margin-top:31px;}}
.question-example {{border-left:2px solid var(--line);padding-left:15px;}}
.question-example strong {{font-size:13px;font-weight:600;color:var(--ink);}}
.question-example p {{font-size:12px;line-height:1.7;color:var(--muted);margin:8px 0;}}
[data-testid="stChatMessage"] {{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:22px 24px;gap:15px;margin:8px 0;}}
[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {{background:transparent;border-color:transparent;padding:12px 24px;}}
[data-testid="stChatMessageAvatarCustom"] {{background:var(--line);border-radius:9px;}}
[data-testid="stChatMessageAvatarCustom"] span {{color:var(--ink)!important;}}
[data-testid="stChatMessage"]:has([aria-label="Chat message from assistant"]) [data-testid="stChatMessageAvatarCustom"] {{background:var(--accent);}}
[data-testid="stChatMessage"]:has([aria-label="Chat message from assistant"]) [data-testid="stChatMessageAvatarCustom"] span {{color:{'#132738' if theme == 'Тёмная' else '#ffffff'}!important;}}
[data-testid="stChatMessageContent"] p,[data-testid="stChatMessageContent"] [data-testid="stText"] {{font-size:var(--body-size);line-height:1.85;color:var(--ink);overflow-wrap:anywhere;}}
[data-testid="stText"] span {{color:var(--ink);font-size:var(--body-size);line-height:1.85;}}
[data-testid="stChatMessageContent"] [data-testid="stCaptionContainer"] p {{font-size:11px;color:var(--muted);}}
[data-testid="stChatMessageContent"] [data-testid="stExpander"] {{background:var(--bg);border:1px solid var(--line);border-radius:9px;}}
[data-testid="stExpander"] summary {{padding:12px 14px;color:var(--ink);}}
[data-testid="stExpander"] summary p {{font-size:12px!important;line-height:1.5!important;}}
[data-testid="stExpanderDetails"] [data-testid="stText"] {{font-size:13px;line-height:1.8;color:var(--muted);white-space:pre-wrap;}}
[data-testid="stExpanderDetails"] [data-testid="stText"] span {{font-size:13px;color:var(--muted);}}
[data-testid="stChatInput"] {{background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:0 6px 26px #122d4510;}}
[data-testid="stChatInput"]>div {{background:var(--surface)!important;border-radius:inherit;}}
[data-testid="stChatInputSubmitButton"]:not(:disabled) {{background:var(--accent);color:{'#132738' if theme == 'Тёмная' else '#ffffff'};}}
[data-testid="stChatInput"]:focus-within {{border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 12%,transparent);}}
[data-testid="stChatInput"] textarea {{background:transparent;font-size:15px;padding:15px 17px;}}
[data-testid="stChatInput"] textarea:focus-visible {{outline:none!important;}}
[data-testid="stBottomBlockContainer"] {{max-width:1030px;padding:14px 3rem 22px;}}
.st-key-login,.st-key-setup {{max-width:460px;margin:7vh auto 0;}}
.st-key-login .brand {{--side-ink:var(--accent);--side-muted:var(--muted);--brand-cut:var(--bg);padding-bottom:30px;}}
.st-key-login .brand>div {{display:none;}}
.st-key-login h1 {{margin-bottom:10px!important;}}
.st-key-login [data-testid="stForm"] {{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:27px;margin:20px 0 8px;box-shadow:0 12px 50px #10283e07;}}
.st-key-login [data-testid="stFormSubmitButton"] button {{width:100%;background:var(--accent);color:white;border:0;min-height:43px;margin-top:10px;}}
.st-key-login [data-testid="stFormSubmitButton"] button p {{color:white!important;}}
@media(max-width:760px) {{.stMainBlockContainer {{padding:1.5rem 1.2rem 1rem;}}[data-testid="stBottomBlockContainer"] {{padding:12px 1rem 18px;}}.question-examples {{grid-template-columns:1fr;gap:14px;}}.workspace-bar {{font-size:11px;margin-bottom:22px;}}h1 {{letter-spacing:-.8px;}}[data-testid="stChatMessage"] {{padding:17px 13px;gap:9px;}}.st-key-login {{margin-top:4vh;}}}}
@media(prefers-reduced-motion:reduce) {{*,*::before,*::after {{transition:none!important;animation:none!important;scroll-behavior:auto!important;}}}}
</style>''', unsafe_allow_html=True)

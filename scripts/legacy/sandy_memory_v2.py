import os
import json
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), 'sandy_memory_db')
TOPICS_JSON = os.path.join(os.path.dirname(__file__), 'sandy_topics_fallback.json')
RAW_JSON = os.path.join(os.path.dirname(__file__), 'sandy_raw_fallback.json')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

USE_CHROMA = False
client = None
topics_col = None
raw_col = None

try:
    if OPENAI_API_KEY:
        from openai import OpenAI
        import chromadb
        from chromadb.utils import embedding_functions
        client = OpenAI(api_key=OPENAI_API_KEY)
        chroma_client = chromadb.PersistentClient(path=DB_PATH)
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=OPENAI_API_KEY,
            model_name='text-embedding-3-small'
        )
        topics_col = chroma_client.get_or_create_collection(name='sandy_topics', embedding_function=openai_ef)
        raw_col = chroma_client.get_or_create_collection(name='sandy_raw', embedding_function=openai_ef)
        USE_CHROMA = True
except Exception as e:
    print(f'[Memory] Chroma disabled, fallback mode enabled: {e}')


def _load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def summarize_and_store(user_text: str, ai_reply: str):
    if not user_text or not ai_reply:
        return

    now = datetime.now()
    timestamp = now.isoformat()
    date_str = now.strftime('%Y-%m-%d')
    doc = f'User: {user_text}\nSandy: {ai_reply}'
    if USE_CHROMA:
        doc_id = f"raw_{now.strftime('%Y%m%d_%H%M%S_%f')}"
        raw_col.add(documents=[doc], metadatas=[{'timestamp': timestamp, 'date': date_str}], ids=[doc_id])
        try:
            response = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {
                        'role': 'system',
                        'content': 'استخرج فقط 1 إلى 3 حقائق مهمة وجديدة من الحوار. كل حقيقة بسطر. إذا لا يوجد شيء مهم اكتب: لا يوجد'
                    },
                    {'role': 'user', 'content': doc}
                ],
                max_tokens=120,
            )
            extracted = (response.choices[0].message.content or '').strip()
            if extracted and extracted != 'لا يوجد':
                facts = [f.strip('- ').strip() for f in extracted.split('\n') if f.strip() and f.strip() != 'لا يوجد']
                for idx, fact in enumerate(facts):
                    fact_id = f"topic_{now.strftime('%Y%m%d_%H%M%S_%f')}_{idx}"
                    topics_col.add(
                        documents=[fact],
                        metadatas=[{'timestamp': timestamp, 'date': date_str, 'source_raw_id': doc_id}],
                        ids=[fact_id],
                    )
        except Exception as e:
            print(f'[Memory] Summarization error: {e}')
        return

    raw = _load_json(RAW_JSON)
    raw.append({'timestamp': timestamp, 'date': date_str, 'document': doc})
    _save_json(RAW_JSON, raw[-80:])

    topics = _load_json(TOPICS_JSON)
    topic_line = user_text.strip()[:140]
    if topic_line:
        topics.append({'timestamp': timestamp, 'date': date_str, 'fact': topic_line})
        _save_json(TOPICS_JSON, topics[-120:])


def recall(query: str, n_topics: int = 5, n_raw: int = 3) -> str:
    if not query:
        return ''

    if USE_CHROMA:
        parts = []
        try:
            topic_res = topics_col.query(query_texts=[query], n_results=max(1, min(n_topics, topics_col.count() or 1)))
            docs = topic_res.get('documents', [[]])[0]
            dists = topic_res.get('distances', [[]])[0]
            relevant_topics = [doc for doc, dist in zip(docs, dists) if dist < 0.6]
            if relevant_topics:
                parts.append('📌 معلومات ذات صلة:\n' + '\n'.join(f'- {t}' for t in relevant_topics[:n_topics]))
        except Exception as e:
            print(f'[Memory] Topic recall error: {e}')

        try:
            raw_res = raw_col.query(query_texts=[query], n_results=max(1, min(n_raw, raw_col.count() or 1)))
            docs = raw_res.get('documents', [[]])[0]
            metas = raw_res.get('metadatas', [[]])[0]
            dists = raw_res.get('distances', [[]])[0]
            relevant_raw = [(doc, meta.get('date', '')) for doc, meta, dist in zip(docs, metas, dists) if dist < 0.5]
            if relevant_raw:
                parts.append('💬 محادثات قريبة:\n' + '\n\n'.join(f'[{d}]\n{doc}' for doc, d in relevant_raw[:n_raw]))
        except Exception as e:
            print(f'[Memory] Raw recall error: {e}')
        return '\n\n'.join(parts)

    query_terms = [t for t in query.lower().split() if len(t) > 2]
    parts = []
    topics = _load_json(TOPICS_JSON)
    if topics:
        hits = [t['fact'] for t in reversed(topics) if any(term in t.get('fact', '').lower() for term in query_terms)]
        if hits:
            parts.append('📌 معلومات ذات صلة:\n' + '\n'.join(f'- {h}' for h in hits[:n_topics]))
    raw = _load_json(RAW_JSON)
    if raw:
        hits = [r for r in reversed(raw) if any(term in r.get('document', '').lower() for term in query_terms)]
        if hits:
            parts.append('💬 محادثات قريبة:\n' + '\n\n'.join(f"[{h.get('date','')}]\n{h.get('document','')}" for h in hits[:n_raw]))
    return '\n\n'.join(parts)


def cleanup_old_raw(days: int = 7):
    cutoff = datetime.now() - timedelta(days=days)
    if USE_CHROMA:
        try:
            all_raw = raw_col.get()
            to_delete = [
                id_ for id_, meta in zip(all_raw.get('ids', []), all_raw.get('metadatas', []))
                if datetime.strptime(meta.get('date', '9999-12-31'), '%Y-%m-%d') < cutoff
            ]
            if to_delete:
                raw_col.delete(ids=to_delete)
        except Exception as e:
            print(f'[Memory] Cleanup error: {e}')
        return

    raw = _load_json(RAW_JSON)
    raw = [r for r in raw if datetime.strptime(r.get('date', '9999-12-31'), '%Y-%m-%d') >= cutoff]
    _save_json(RAW_JSON, raw)
    
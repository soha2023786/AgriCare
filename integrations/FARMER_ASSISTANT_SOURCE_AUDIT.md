# Farmer Assistant source audit and AgriCare integration map

Source reviewed: https://github.com/Abhishekpendyala06/Farmer-Assistant-Multilingual-Chatbot

The source project is a separate Flask application. Its `farmer-chatbot/server.py` exposes these backend routes:

- `POST /api/disease` — image-based disease flow / treatment lookup.
- `GET /api/price` — market-price lookup.
- `GET /api/health` — backend health.

The multilingual chat interaction is primarily in the browser-side `chatbot.js` and language response dictionaries (`responses_en.json`, `responses_hi.json`, `responses_te.json`), rather than a dedicated server-side conversation endpoint. This is why AgriCare does not run a second Flask server and does not embed the deployed Farmer Assistant website in an iframe.

## Unified AgriCare endpoints

| Farmer Assistant source capability | AgriCare endpoint / implementation |
|---|---|
| Multilingual chat | `POST /api/assistant` |
| English / Hindi / Telugu selection | `AssistantInput.language` and language-locked LLM / fallback responses |
| Follow-up conversation | `conversation_id` plus SQLite `assistant_conversations` history |
| Crop and soil advice | `/api/assistant` and structured `/api/disease/guidance` crop-growing context |
| Disease information | `POST /api/disease/guidance` |
| Optional image screening | `POST /api/pest/detect` (requires `PLANTNET_API_KEY`) |
| Weather | `/api/weather/current` and assistant weather tool context |
| Historical mandi data | `/api/market/historical` and `/api/market/historical/export` |
| Farmer income / expense context | Authenticated `/api/analytics/overview`, only passed to assistant for a signed-in farmer |
| Health | `/api/health` |

## Scope note

The original response dictionaries and every original frontend interaction have not been copied wholesale. The AgriCare assistant provides the core three-language conversation, voice input/output, context persistence and backend module routing, but it is a scoped migration of the capabilities rather than a byte-for-byte merge of the entire Farmer Assistant source repository. The source's full static rule bank and any additional frontend-only tools would need a separate content migration and regression pass if exact response parity is required.

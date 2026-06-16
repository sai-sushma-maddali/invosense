# invo-frontend

Invoice-decision pipeline — pay on Base Sepolia, publish to cited.md, display on an OpenUI dashboard.

> **TESTNET ONLY.** All payments run on Base Sepolia. Mainnet is hard-blocked in code.

---

## Quick start

```bash
cd invo_frontend
npm install
cp .env.example .env          # fill in your keys (see below)
npm run build:client          # bundle the React dashboard once
npm run dev                   # starts Express + watches server TS
```

Open `http://localhost:3000`. Mock decisions load automatically from `mocks/decisions.json`.

---

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `PORT` | No | Default `3000` |
| `CDP_API_KEY` | For real payments | Coinbase CDP project key |
| `CDP_WALLET_ID` | For real payments | Pre-funded Base Sepolia wallet |
| `WALLET_PRIVATE_KEY` | For real payments | Private key of the test wallet — **never commit** |
| `CITED_API_URL` | No | Leave blank to use the built-in stub |
| `CITED_API_KEY` | No | Bearer token for cited.md |
| `MOCK_FX_MYR_TO_USDC` | No | Default `0.22`. **Mock rate only.** |
| `X402_RECIPIENT` | No | Override the testnet USDC recipient (defaults to burn address) |

---

## Faucet funding — Base Sepolia

1. Create a wallet (e.g. MetaMask or cast from Foundry).
2. Copy the private key → `WALLET_PRIVATE_KEY` in `.env`.
3. Get the wallet address: `cast wallet address --private-key $WALLET_PRIVATE_KEY`
4. Paste the address at **<https://faucet.quicknode.com/base/sepolia>** and request test ETH.
5. For USDC: use Circle's testnet faucet at **<https://faucet.circle.com>** (select Base Sepolia).
6. Verify balance: `cast balance <your-address> --rpc-url https://sepolia.base.org`

---

## Swapping the cited.md stub for the real endpoint

By default, when `CITED_API_URL` is unset, `src/lib/cited.ts` returns a mock URL so
the pipeline runs without credentials. To publish for real:

1. Sign up at [cited.md](https://cited.md) and obtain an API key.
2. Set in `.env`:
   ```
   CITED_API_URL=https://api.cited.md/v1/publish
   CITED_API_KEY=sk_your_key_here
   ```
3. Restart the server. The `citedPublish` wrapper will send real HTTP POST requests.

---

## Render deployment

1. Fork / push this repo to GitHub.
2. In [Render](https://render.com), click **New → Web Service** and connect the repo.
3. Render picks up `render.yaml` automatically.
4. Set the secret env vars in the Render dashboard (**Environment** tab):
   - `CDP_API_KEY`
   - `CDP_WALLET_ID`
   - `WALLET_PRIVATE_KEY`
   - `CITED_API_URL`
   - `CITED_API_KEY`
5. Deploy. The build command runs `npm ci && npm run build`; the start command runs `node dist/server.js`.

---

## Project structure

```
invo_frontend/
├── src/
│   ├── actions/
│   │   ├── pay.ts          # actions.pay()  — x402 + CDP, Base Sepolia only
│   │   └── publish.ts      # actions.publish() — posts to cited.md
│   ├── api/
│   │   └── invoices.ts     # in-memory invoice store + route handlers
│   ├── ui/
│   │   ├── dashboard.tsx   # entire OpenUI frontend
│   │   └── index.tsx       # React entry point
│   ├── lib/
│   │   ├── cited.ts        # thin cited.md wrapper (stub-safe)
│   │   └── wallet.ts       # CDP/viem wallet helper + mainnet guard
│   └── server.ts           # Express entry point
├── mocks/
│   └── decisions.json      # 5 sample decisions (2 PAY, 1 FLAG, 2 HUMAN_REVIEW)
├── public/
│   ├── index.html
│   └── bundle.js           # built by esbuild (git-ignored)
├── .env.example
├── esbuild.mjs             # client bundler config
├── render.yaml
├── package.json
└── tsconfig.json
```

---

## API reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/invoices` | Returns all `InvoiceRecord[]` with current status |
| `POST` | `/invoices/:id/approve` | Run `pay()` + `publish()` for a HUMAN_REVIEW invoice |
| `POST` | `/invoices/:id/reject` | Mark HUMAN_REVIEW invoice as REJECTED (no payment) |

---

## Safety notes

- `pay.ts` calls `requireBaseSepolia()` at line 1 — throws `MAINNET BLOCKED` if the network is wrong.
- `WALLET_PRIVATE_KEY` is read from env only, never logged or serialised.
- `mocks/decisions.json` contains no real credentials.
- Mock FX rate (1 MYR = 0.22 USDC) is labelled in code comments, UI tooltips, and the transaction log.

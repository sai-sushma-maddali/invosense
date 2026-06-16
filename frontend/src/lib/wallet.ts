import "dotenv/config";
import { createWalletClient, http, type WalletClient, type Account } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { baseSepolia } from "viem/chains";

// The ONLY network permitted for this service.
export const REQUIRED_NETWORK = "base-sepolia" as const;

/**
 * Returns a viem WalletClient pre-configured for Base Sepolia.
 * Throws if WALLET_PRIVATE_KEY is missing.
 */
export function getTestWalletClient(): { client: WalletClient; account: Account } {
  const rawKey = process.env.WALLET_PRIVATE_KEY;

  if (!rawKey) {
    throw new Error(
      "WALLET_PRIVATE_KEY is not set. " +
        "Fund a test wallet at https://faucet.quicknode.com/base/sepolia and add the private key to .env"
    );
  }

  // Normalise: viem requires a 0x-prefixed hex string
  const pk = (rawKey.startsWith("0x") ? rawKey : `0x${rawKey}`) as `0x${string}`;
  const account = privateKeyToAccount(pk);

  const client = createWalletClient({
    account,
    chain: baseSepolia,
    transport: http(),
  });

  return { client, account };
}

/**
 * Guard: hard-fail if the caller tries to use any chain other than base-sepolia.
 * Called at the top of every payment function.
 */
export function requireBaseSepolia(network: string): void {
  if (network !== REQUIRED_NETWORK) {
    throw new Error(
      `MAINNET BLOCKED — attempted to use network "${network}". ` +
        `Only "${REQUIRED_NETWORK}" is permitted.`
    );
  }
}

/** Address of the test wallet (derived from WALLET_PRIVATE_KEY). */
export function getTestWalletAddress(): `0x${string}` | null {
  const rawKey = process.env.WALLET_PRIVATE_KEY;
  if (!rawKey) return null;
  try {
    const pk = (rawKey.startsWith("0x") ? rawKey : `0x${rawKey}`) as `0x${string}`;
    return privateKeyToAccount(pk).address;
  } catch {
    return null;
  }
}

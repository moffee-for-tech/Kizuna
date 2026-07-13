"use client";

import { useEffect, useState } from "react";
import {
  TwoFactorStatus,
  TwoFactorSetupPayload,
  getTwoFactorStatus,
  setupTwoFactor,
  verifyTwoFactor,
  disableTwoFactor,
  regenerateBackupCodes,
} from "@/lib/api";

type View =
  | { kind: "loading" }
  | { kind: "status"; status: TwoFactorStatus }
  | { kind: "enroll"; payload: TwoFactorSetupPayload; verifyCode: string; error: string }
  | { kind: "show-codes"; codes: string[]; afterEnable: boolean }
  | { kind: "disable"; password: string; code: string; error: string }
  | { kind: "regenerate"; password: string; code: string; error: string };

export function TwoFactorSettings({ onClose }: { onClose: () => void }) {
  const [view, setView] = useState<View>({ kind: "loading" });

  const refresh = async () => {
    setView({ kind: "loading" });
    try {
      const status = await getTwoFactorStatus();
      setView({ kind: "status", status });
    } catch {
      setView({ kind: "status", status: { enabled: false, enabled_at: null, backup_codes_remaining: 0 } });
    }
  };

  useEffect(() => { refresh(); }, []);

  const startEnroll = async () => {
    try {
      const payload = await setupTwoFactor();
      setView({ kind: "enroll", payload, verifyCode: "", error: "" });
    } catch (err: any) {
      alert(err.message || "Failed to start setup");
    }
  };

  const submitVerify = async () => {
    if (view.kind !== "enroll") return;
    try {
      await verifyTwoFactor(view.verifyCode.trim());
      setView({ kind: "show-codes", codes: view.payload.backup_codes, afterEnable: true });
    } catch (err: any) {
      setView({ ...view, error: err.message || "Invalid code" });
    }
  };

  const submitDisable = async () => {
    if (view.kind !== "disable") return;
    try {
      await disableTwoFactor(view.password, view.code.trim());
      await refresh();
    } catch (err: any) {
      setView({ ...view, error: err.message || "Failed to disable" });
    }
  };

  const submitRegenerate = async () => {
    if (view.kind !== "regenerate") return;
    try {
      const { backup_codes } = await regenerateBackupCodes(view.password, view.code.trim());
      setView({ kind: "show-codes", codes: backup_codes, afterEnable: false });
    } catch (err: any) {
      setView({ ...view, error: err.message || "Failed to regenerate" });
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="2fa-title"
      onClick={onClose}
    >
      <div
        className="bg-[#3a3a36] border border-[#4a4a44] rounded-xl w-full max-w-md mx-4 max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-5 border-b border-[#4a4a44] flex items-center justify-between">
          <h2 id="2fa-title" className="text-xl font-medium text-[#e8e4dd]">
            Two-factor authentication
          </h2>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-[#454540] flex items-center justify-center text-[#a8a49d] hover:text-[#e8e4dd] transition-colors"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="p-6">
          {view.kind === "loading" && (
            <p className="text-sm text-[#a8a49d]">Loading…</p>
          )}

          {view.kind === "status" && !view.status.enabled && (
            <>
              <p className="text-sm text-[#a8a49d] mb-4">
                Add an extra layer of security to your account. You&apos;ll need an authenticator
                app like Google Authenticator, Microsoft Authenticator, Authy, or 1Password.
              </p>
              <button
                onClick={startEnroll}
                className="w-full py-2.5 bg-[#d4a574] hover:bg-[#e0b88a] rounded-lg font-medium text-[#2f2f2c] transition-colors text-sm"
              >
                Enable two-factor authentication
              </button>
            </>
          )}

          {view.kind === "status" && view.status.enabled && (
            <>
              <div className="flex items-center gap-2 mb-4 px-3 py-2 bg-[#2f2f2c] rounded-lg">
                <span className="w-2 h-2 rounded-full bg-[#6dcba1]" />
                <span className="text-sm text-[#e8e4dd]">
                  2FA is active · {view.status.backup_codes_remaining} backup codes remaining
                </span>
              </div>
              <div className="space-y-2">
                <button
                  onClick={() => setView({ kind: "regenerate", password: "", code: "", error: "" })}
                  className="w-full py-2.5 bg-[#454540] hover:bg-[#525248] rounded-lg font-medium text-[#e8e4dd] transition-colors text-sm"
                >
                  Regenerate backup codes
                </button>
                <button
                  onClick={() => setView({ kind: "disable", password: "", code: "", error: "" })}
                  className="w-full py-2.5 bg-[#3a2a2a] hover:bg-[#4a3030] rounded-lg font-medium text-[#f87171] transition-colors text-sm"
                >
                  Disable two-factor authentication
                </button>
              </div>
            </>
          )}

          {view.kind === "enroll" && (
            <>
              <p className="text-sm text-[#a8a49d] mb-3">
                1. Scan this QR code with your authenticator app.
              </p>
              <div className="flex justify-center mb-4">
                <img
                  src={`data:image/png;base64,${view.payload.qr_code_png_b64}`}
                  alt="2FA QR code"
                  className="w-48 h-48 bg-white p-2 rounded-lg"
                />
              </div>
              <details className="mb-4 text-xs text-[#a8a49d]">
                <summary className="cursor-pointer hover:text-[#e8e4dd]">Can&apos;t scan? Enter code manually</summary>
                <code className="block mt-2 px-3 py-2 bg-[#2f2f2c] rounded text-[#e8e4dd] break-all font-mono">
                  {view.payload.secret}
                </code>
              </details>

              <p className="text-sm text-[#a8a49d] mb-2">
                2. Enter the 6-digit code your app shows.
              </p>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                autoFocus
                value={view.verifyCode}
                onChange={(e) => setView({ ...view, verifyCode: e.target.value, error: "" })}
                className="w-full px-3.5 py-2.5 bg-[#2f2f2c] border border-[#4a4a44] rounded-lg text-[#e8e4dd] text-center font-mono tracking-widest mb-3"
                placeholder="123456"
              />
              {view.error && (
                <p className="text-sm text-[#f87171] mb-3">{view.error}</p>
              )}
              <div className="flex gap-2">
                <button
                  onClick={() => refresh()}
                  className="flex-1 py-2.5 bg-[#454540] hover:bg-[#525248] rounded-lg text-sm text-[#e8e4dd]"
                >
                  Cancel
                </button>
                <button
                  onClick={submitVerify}
                  disabled={view.verifyCode.length !== 6}
                  className="flex-1 py-2.5 bg-[#d4a574] hover:bg-[#e0b88a] rounded-lg font-medium text-[#2f2f2c] text-sm disabled:opacity-50"
                >
                  Verify and enable
                </button>
              </div>
            </>
          )}

          {view.kind === "show-codes" && (
            <>
              {view.afterEnable && (
                <div className="mb-3 px-3 py-2 bg-[#1f3a2a] rounded-lg text-sm text-[#6dcba1]">
                  ✓ Two-factor authentication is now enabled.
                </div>
              )}
              <p className="text-sm text-[#a8a49d] mb-3">
                Save these backup codes somewhere safe. Each code works once. You can use them to
                sign in if you lose access to your authenticator app.
              </p>
              <div className="grid grid-cols-2 gap-2 mb-4">
                {view.codes.map((c) => (
                  <code
                    key={c}
                    className="px-2 py-1.5 bg-[#2f2f2c] rounded text-center text-sm text-[#e8e4dd] font-mono"
                  >
                    {c}
                  </code>
                ))}
              </div>
              <button
                onClick={() => navigator.clipboard?.writeText(view.codes.join("\n"))}
                className="w-full py-2 mb-2 bg-[#454540] hover:bg-[#525248] rounded-lg text-sm text-[#e8e4dd]"
              >
                Copy all to clipboard
              </button>
              <button
                onClick={refresh}
                className="w-full py-2.5 bg-[#d4a574] hover:bg-[#e0b88a] rounded-lg font-medium text-[#2f2f2c] text-sm"
              >
                I&apos;ve saved them
              </button>
            </>
          )}

          {(view.kind === "disable" || view.kind === "regenerate") && (
            <>
              <p className="text-sm text-[#a8a49d] mb-4">
                {view.kind === "disable"
                  ? "Confirm your password and a current 2FA code to disable."
                  : "Confirm your password and a current 2FA code. All previous backup codes will stop working."}
              </p>
              <label className="block text-sm text-[#a8a49d] mb-1.5">Password</label>
              <input
                type="password"
                value={view.password}
                onChange={(e) => setView({ ...view, password: e.target.value, error: "" })}
                className="w-full px-3.5 py-2.5 mb-3 bg-[#2f2f2c] border border-[#4a4a44] rounded-lg text-[#e8e4dd]"
              />
              <label className="block text-sm text-[#a8a49d] mb-1.5">2FA code or backup code</label>
              <input
                type="text"
                inputMode="text"
                autoComplete="one-time-code"
                value={view.code}
                onChange={(e) => setView({ ...view, code: e.target.value, error: "" })}
                className="w-full px-3.5 py-2.5 mb-3 bg-[#2f2f2c] border border-[#4a4a44] rounded-lg text-[#e8e4dd] font-mono"
                placeholder="123456"
              />
              {view.error && (
                <p className="text-sm text-[#f87171] mb-3">{view.error}</p>
              )}
              <div className="flex gap-2">
                <button
                  onClick={() => refresh()}
                  className="flex-1 py-2.5 bg-[#454540] hover:bg-[#525248] rounded-lg text-sm text-[#e8e4dd]"
                >
                  Cancel
                </button>
                <button
                  onClick={view.kind === "disable" ? submitDisable : submitRegenerate}
                  disabled={!view.password || !view.code}
                  className={`flex-1 py-2.5 rounded-lg font-medium text-sm disabled:opacity-50 ${
                    view.kind === "disable"
                      ? "bg-[#f87171] hover:bg-[#fa8888] text-[#2f2f2c]"
                      : "bg-[#d4a574] hover:bg-[#e0b88a] text-[#2f2f2c]"
                  }`}
                >
                  {view.kind === "disable" ? "Disable 2FA" : "Generate new codes"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

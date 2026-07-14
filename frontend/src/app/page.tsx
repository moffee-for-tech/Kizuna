"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function LoginPage() {
  const { login, loginWith2fa, user, loading } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [code, setCode] = useState("");

  useEffect(() => {
    if (!loading && user) router.push("/chat");
  }, [user, loading, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const result = await login(email, password);
      if (result.requires2fa) {
        setChallengeToken(result.challengeToken);
      } else {
        router.push("/chat");
      }
    } catch (err: any) {
      const msg = err.message;
      setError(msg === "Invalid email or password" ? msg : "Login failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handle2faSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!challengeToken) return;
    setError("");
    setIsLoading(true);
    try {
      await loginWith2fa(challengeToken, code.trim());
      router.push("/chat");
    } catch (err: any) {
      setError(err.message || "Verification failed");
    } finally {
      setIsLoading(false);
    }
  };

  const cancel2fa = () => {
    setChallengeToken(null);
    setCode("");
    setError("");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-[#a8a49d]">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-semibold text-[#e8e4dd] tracking-tight">
            Kizuna
          </h1>
          <p className="text-[#a8a49d] text-sm mt-2">AI-Powered Chat Platform</p>
        </div>

        <div className="bg-[#3a3a36] border border-[#4a4a44] rounded-xl p-8">
          {!challengeToken ? (
            <>
              <h2 className="text-lg font-medium mb-6 text-[#e8e4dd]">Sign in</h2>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm text-[#a8a49d] mb-1.5">Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-3.5 py-2.5 bg-[#2f2f2c] border border-[#4a4a44] rounded-lg text-[#e8e4dd] placeholder-[#7a776f] focus:outline-none focus:border-[#d4a574] transition-colors text-sm"
                    placeholder="you@company.com"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm text-[#a8a49d] mb-1.5">Password</label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-3.5 py-2.5 bg-[#2f2f2c] border border-[#4a4a44] rounded-lg text-[#e8e4dd] placeholder-[#7a776f] focus:outline-none focus:border-[#d4a574] transition-colors text-sm"
                    placeholder="Enter your password"
                    required
                  />
                </div>

                {error && (
                  <div className="text-[#f87171] text-sm bg-[#f8717115] px-3.5 py-2.5 rounded-lg">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full py-2.5 bg-[#d4a574] hover:bg-[#e0b88a] rounded-lg font-medium text-[#2f2f2c] transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm mt-2"
                >
                  {isLoading ? "Signing in..." : "Sign in"}
                </button>
              </form>

              <p className="text-center text-sm text-[#a8a49d] mt-6">
                Don&apos;t have an account?{" "}
                <a href="/register" className="text-[#d4a574] hover:text-[#e0b88a] transition-colors">
                  Sign up
                </a>
              </p>
            </>
          ) : (
            <>
              <h2 className="text-lg font-medium mb-2 text-[#e8e4dd]">Two-factor authentication</h2>
              <p className="text-sm text-[#a8a49d] mb-6">
                Enter the 6-digit code from your authenticator app, or one of your backup codes.
              </p>

              <form onSubmit={handle2faSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm text-[#a8a49d] mb-1.5">Code</label>
                  <input
                    type="text"
                    inputMode="text"
                    autoComplete="one-time-code"
                    autoFocus
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    className="w-full px-3.5 py-2.5 bg-[#2f2f2c] border border-[#4a4a44] rounded-lg text-[#e8e4dd] placeholder-[#7a776f] focus:outline-none focus:border-[#d4a574] transition-colors text-sm tracking-widest text-center font-mono"
                    placeholder="123456"
                    maxLength={20}
                    required
                  />
                </div>

                {error && (
                  <div className="text-[#f87171] text-sm bg-[#f8717115] px-3.5 py-2.5 rounded-lg">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full py-2.5 bg-[#d4a574] hover:bg-[#e0b88a] rounded-lg font-medium text-[#2f2f2c] transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm mt-2"
                >
                  {isLoading ? "Verifying..." : "Verify"}
                </button>

                <button
                  type="button"
                  onClick={cancel2fa}
                  className="w-full py-2 text-sm text-[#a8a49d] hover:text-[#e8e4dd] transition-colors"
                >
                  Use a different account
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

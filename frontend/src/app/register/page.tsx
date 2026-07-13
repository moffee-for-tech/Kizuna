"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const DEPARTMENTS = [
  { value: "admin", label: "Admin" },
  { value: "sales", label: "Sales" },
  { value: "operations", label: "Operations" },
  { value: "finance", label: "Finance" },
  { value: "executive", label: "Executive" },
];

export default function RegisterPage() {
  const { register, user, loading } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [department, setDepartment] = useState("admin");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!loading && user) router.push("/chat");
  }, [user, loading, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/[0-9]/.test(password)) {
      setError("Password must include uppercase, lowercase, and a number");
      return;
    }

    setIsLoading(true);
    try {
      await register(email, password, name, department);
      router.push("/chat");
    } catch (err: any) {
      console.error("Registration failed:", err);
      setError("Registration failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
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
          <h1 className="text-3xl font-semibold text-[#e8e4dd] tracking-tight">Polaris</h1>
          <p className="text-[#a8a49d] text-sm mt-2">Create your account</p>
        </div>

        <div className="bg-[#3a3a36] border border-[#4a4a44] rounded-xl p-8">
          <h2 className="text-lg font-medium mb-6 text-[#e8e4dd]">Sign up</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-[#a8a49d] mb-1.5">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-[#2f2f2c] border border-[#4a4a44] rounded-lg text-[#e8e4dd] placeholder-[#7a776f] focus:outline-none focus:border-[#d4a574] transition-colors text-sm"
                placeholder="Your name"
                required
              />
            </div>
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
              <label className="block text-sm text-[#a8a49d] mb-1.5">Department</label>
              <select
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-[#2f2f2c] border border-[#4a4a44] rounded-lg text-[#e8e4dd] focus:outline-none focus:border-[#d4a574] transition-colors text-sm"
              >
                {DEPARTMENTS.map((d) => (
                  <option key={d.value} value={d.value}>{d.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-[#a8a49d] mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-[#2f2f2c] border border-[#4a4a44] rounded-lg text-[#e8e4dd] placeholder-[#7a776f] focus:outline-none focus:border-[#d4a574] transition-colors text-sm"
                placeholder="At least 8 characters"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-[#a8a49d] mb-1.5">Confirm password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-[#2f2f2c] border border-[#4a4a44] rounded-lg text-[#e8e4dd] placeholder-[#7a776f] focus:outline-none focus:border-[#d4a574] transition-colors text-sm"
                placeholder="Confirm your password"
                required
              />
            </div>

            {error && (
              <div className="text-[#f87171] text-sm bg-[#f8717115] px-3.5 py-2.5 rounded-lg">{error}</div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 bg-[#d4a574] hover:bg-[#e0b88a] rounded-lg font-medium text-[#2f2f2c] transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm mt-2"
            >
              {isLoading ? "Creating account..." : "Create account"}
            </button>
          </form>

          <p className="text-center text-sm text-[#a8a49d] mt-6">
            Already have an account?{" "}
            <a href="/" className="text-[#d4a574] hover:text-[#e0b88a] transition-colors">Sign in</a>
          </p>
        </div>
      </div>
    </div>
  );
}

"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { logoutApi, API_URL } from "@/lib/api";

interface User {
  id: string;
  email: string;
  name: string;
  department: string;
  created_at: string;
}

export type LoginResult =
  | { requires2fa: false }
  | { requires2fa: true; challengeToken: string };

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  loginWith2fa: (challengeToken: string, code: string) => Promise<void>;
  register: (email: string, password: string, name: string, department: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);



export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000); // 5s timeout

    fetch(`${API_URL}/api/auth/me`, {
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (res) => {
        if (res.ok) {
          const userData = await res.json();
          setUser(userData);
          setToken("cookie");
        }
      })
      .catch(() => {
        // Backend unreachable or timeout — user stays null
      })
      .finally(() => {
        clearTimeout(timeout);
        setLoading(false);
      });

    return () => {
      controller.abort();
      clearTimeout(timeout);
    };
  }, []);

  const login = async (email: string, password: string): Promise<LoginResult> => {
    const res = await fetch(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      credentials: "include",
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Login failed");
    }

    const data = await res.json();
    if (data.requires_2fa) {
      return { requires2fa: true, challengeToken: data.challenge_token };
    }
    setToken("cookie");
    setUser(data.user);
    return { requires2fa: false };
  };

  const loginWith2fa = async (challengeToken: string, code: string) => {
    const res = await fetch(`${API_URL}/api/auth/login/2fa`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_token: challengeToken, code }),
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "2FA verification failed");
    }
    const data = await res.json();
    setToken("cookie");
    setUser(data.user);
  };

  const register = async (email: string, password: string, name: string, department: string) => {
    const res = await fetch(`${API_URL}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, name, department }),
      credentials: "include",
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Registration failed");
    }

    const data = await res.json();
    setToken("cookie");
    setUser(data.user);
  };

  const logout = async () => {
    try {
      await logoutApi(); // Server-side token revocation + cookie clear
    } catch {
      // Clear client state regardless
    }
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, loginWith2fa, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}

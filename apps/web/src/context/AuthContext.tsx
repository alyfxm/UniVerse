"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { fetchDemoToken, fetchMyProfile } from "@/lib/api";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { SupportedLanguage, UserProfile, UserRole } from "@/types/api";

interface AuthContextValue {
  user: UserProfile | null;
  token: string | null;
  isLoading: boolean;
  error: string | null;
  loginWithDemoRole: (
    role: UserRole,
    preferredLanguage?: SupportedLanguage
  ) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const STORAGE_TOKEN_KEY = "universe_auth_token";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loginWithDemoRole = useCallback(
    async (role: UserRole, preferredLanguage: SupportedLanguage = "en") => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await fetchDemoToken(role, preferredLanguage);
        setToken(res.access_token);
        setUser(res.user);
        if (typeof window !== "undefined") {
          window.localStorage.setItem(STORAGE_TOKEN_KEY, res.access_token);
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Authentication failed"
        );
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const logout = useCallback(async () => {
    const supabase = getSupabaseBrowserClient();
    if (supabase) {
      await supabase.auth.signOut();
    }
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(STORAGE_TOKEN_KEY);
    }
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    let mounted = true;

    async function bootstrapAuth() {
      try {
        // 1. Check live Supabase session if configured
        const supabase = getSupabaseBrowserClient();
        if (supabase) {
          const { data } = await supabase.auth.getSession();
          const accessToken = data.session?.access_token;
          if (accessToken && mounted) {
            const profile = await fetchMyProfile(accessToken);
            setToken(accessToken);
            setUser(profile);
            setIsLoading(false);
            return;
          }
        }

        // 2. Check persisted token in localStorage
        if (typeof window !== "undefined") {
          const savedToken = window.localStorage.getItem(STORAGE_TOKEN_KEY);
          if (savedToken) {
            try {
              const profile = await fetchMyProfile(savedToken);
              if (mounted) {
                setToken(savedToken);
                setUser(profile);
                setIsLoading(false);
                return;
              }
            } catch {
              window.localStorage.removeItem(STORAGE_TOKEN_KEY);
            }
          }
        }

        // 3. Auto-bootstrap Demo Student session for frictionless campus preview
        await loginWithDemoRole("student", "en");
      } catch {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    bootstrapAuth();
    return () => {
      mounted = false;
    };
  }, [loginWithDemoRole]);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        error,
        loginWithDemoRole,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}


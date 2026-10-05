import { createContext, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = loading, false = unauthenticated
  const [needsSetup, setNeedsSetup] = useState(false);
  const [ready, setReady] = useState(false);

  const checkSetup = async () => {
    try {
      const { data } = await api.get("/auth/setup-status");
      setNeedsSetup(data.needs_setup);
    } catch {
      setNeedsSetup(false);
    }
  };

  useEffect(() => {
    const token = localStorage.getItem("ct_token");
    if (!token) {
      checkSetup().then(() => {
        setUser(false);
        setReady(true);
      });
      return;
    }
    api
      .get("/auth/me")
      .then((r) => setUser(r.data))
      .catch(async () => {
        localStorage.removeItem("ct_token");
        await checkSetup();
        setUser(false);
      })
      .finally(() => setReady(true));
  }, []);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("ct_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const setup = async (name, email, password) => {
    const { data } = await api.post("/auth/setup", { name, email, password });
    localStorage.setItem("ct_token", data.token);
    setNeedsSetup(false);
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem("ct_token");
    setUser(false);
    window.location.href = "/login";
  };

  const can = (perm) => !!user && Array.isArray(user.permissions) && user.permissions.includes(perm);

  return (
    <AuthContext.Provider value={{ user, ready, needsSetup, login, setup, logout, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import { Toaster } from "./components/ui/sonner";
import { Loader2 } from "lucide-react";

function Gate() {
  const { user, booting } = useAuth();
  if (booting || user === null) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0b0f17]">
        <Loader2 className="h-6 w-6 animate-spin text-blue-400" />
      </div>
    );
  }
  return user ? <Dashboard /> : <Navigate to="/login" replace />;
}

function LoginGate() {
  const { user, booting } = useAuth();
  if (booting) return null;
  return user ? <Navigate to="/" replace /> : <Login />;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginGate />} />
          <Route path="/" element={<Gate />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" theme="dark" richColors />
    </AuthProvider>
  );
}

export default App;

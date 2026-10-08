import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { ScanLine, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("inspector@indigo.com");
  const [password, setPassword] = useState("inspect123");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(email, password);
      toast.success("Signed in");
    } catch (err) {
      const d = err?.response?.data?.detail;
      setError(typeof d === "string" ? d : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-stretch bg-[#0b0f17] grid-dots">
      {/* Left brand panel */}
      <div className="hidden lg:flex flex-col justify-between w-[46%] p-12 relative overflow-hidden border-r border-white/10">
        <div
          className="absolute inset-0 opacity-25"
          style={{
            backgroundImage:
              "url(https://images.unsplash.com/photo-1748000970909-845f4aa144d2?crop=entropy&cs=srgb&fm=jpg&q=85)",
            backgroundSize: "cover",
            backgroundPosition: "center",
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0b0f17] via-[#0b0f17]/70 to-transparent" />
        <div className="relative z-10 flex items-center gap-3">
          <div className="h-11 w-11 rounded-xl bg-blue-500 flex items-center justify-center glow-primary">
            <ScanLine className="h-6 w-6 text-white" />
          </div>
          <span className="font-display text-2xl font-bold tracking-tight">InspectAI</span>
        </div>
        <div className="relative z-10 space-y-5">
          <h1 className="font-display text-4xl font-bold leading-tight">
            Photos in.
            <br />
            Audit-ready reports out.
          </h1>
          <p className="text-slate-300 max-w-md leading-relaxed">
            Upload a batch of product &amp; packaging photos. We identify each design, count
            visible units, read labels, flag defects, and compile a formatted Excel inspection
            report — never inventing what the photos can&apos;t prove.
          </p>
          <div className="flex items-center gap-2 text-sm text-emerald-400">
            <ShieldCheck className="h-4 w-4" /> Truthful QC — unresolved fields stay unresolved
          </div>
        </div>
      </div>

      {/* Right form */}
      <div className="flex-1 flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-6 animate-rise" data-testid="login-form">
          <div className="lg:hidden flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-xl bg-blue-500 flex items-center justify-center">
              <ScanLine className="h-5 w-5 text-white" />
            </div>
            <span className="font-display text-xl font-bold">InspectAI</span>
          </div>
          <div>
            <h2 className="font-display text-2xl font-semibold">Team sign in</h2>
            <p className="text-sm text-slate-400 mt-1">Buying house inspection console</p>
          </div>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                data-testid="login-email-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="bg-slate-900/60 border-white/10 h-11"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                data-testid="login-password-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-slate-900/60 border-white/10 h-11"
                required
              />
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-400" data-testid="login-error">
              {error}
            </p>
          )}

          <Button
            type="submit"
            data-testid="login-submit-button"
            disabled={loading}
            className="w-full h-11 bg-blue-500 hover:bg-blue-600 text-white font-medium"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Enter console"}
          </Button>

          <p className="text-xs text-slate-500 text-center">
            Demo login prefilled · inspector@indigo.com
          </p>
        </form>
      </div>
    </div>
  );
}

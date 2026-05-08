import { StatusBar } from "expo-status-bar";
import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

const API_BASE_URL = "https://techa-backend.onrender.com";

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    ...options,
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join("\n")
      : detail || "A chamada falhou.";
    throw new Error(message);
  }

  return data;
}

export default function App() {
  const [mode, setMode] = useState("login");
  const [apiStatus, setApiStatus] = useState(null);
  const [loadingHealth, setLoadingHealth] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [token, setToken] = useState("");
  const [user, setUser] = useState(null);
  const [form, setForm] = useState({
    name: "Jefferson Teste",
    email: `teste-${Date.now()}@techa.app`,
    password: "123456",
  });

  const isRegister = mode === "register";
  const canSubmit = useMemo(() => {
    return form.email.trim() && form.password.trim() && (!isRegister || form.name.trim());
  }, [form, isRegister]);

  async function loadHealth() {
    setLoadingHealth(true);
    try {
      const health = await apiRequest("/health");
      setApiStatus(health);
    } catch (error) {
      setApiStatus({ status: "error", database: "unknown", message: error.message });
    } finally {
      setLoadingHealth(false);
    }
  }

  async function loadMe(nextToken) {
    const profile = await apiRequest("/api/v1/auth/me", { token: nextToken });
    setUser(profile);
  }

  async function submit() {
    if (!canSubmit || submitting) return;

    setSubmitting(true);
    setMessage("");

    try {
      if (isRegister) {
        await apiRequest("/api/v1/auth/register", {
          method: "POST",
          body: JSON.stringify({
            name: form.name.trim(),
            email: form.email.trim(),
            password: form.password,
          }),
        });
      }

      const login = await apiRequest("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: form.email.trim(),
          password: form.password,
        }),
      });

      setToken(login.access_token);
      await loadMe(login.access_token);
      setMessage(isRegister ? "Conta criada e login feito." : "Login feito com sucesso.");
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  function updateForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function switchMode(nextMode) {
    setMode(nextMode);
    setMessage("");
    setUser(null);
    setToken("");

    if (nextMode === "register") {
      setForm((current) => ({
        ...current,
        email: `teste-${Date.now()}@techa.app`,
      }));
    }
  }

  useEffect(() => {
    loadHealth();
  }, []);

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="light" />
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.keyboard}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <Text style={styles.title}>Techa</Text>
            <Text style={styles.subtitle}>Cliente mobile de teste conectado ao Render</Text>
          </View>

          <View style={styles.statusPanel}>
            <View>
              <Text style={styles.label}>API</Text>
              <Text style={styles.statusText}>
                {loadingHealth ? "Verificando..." : `${apiStatus?.status || "offline"}`}
              </Text>
              <Text style={styles.statusHint}>
                Banco: {loadingHealth ? "..." : apiStatus?.database || "desconhecido"}
              </Text>
            </View>
            <Pressable style={styles.iconButton} onPress={loadHealth}>
              {loadingHealth ? <ActivityIndicator color="#e8fff6" /> : <Text style={styles.iconText}>↻</Text>}
            </Pressable>
          </View>

          <View style={styles.tabs}>
            <Pressable
              style={[styles.tab, mode === "login" && styles.tabActive]}
              onPress={() => switchMode("login")}
            >
              <Text style={[styles.tabText, mode === "login" && styles.tabTextActive]}>Login</Text>
            </Pressable>
            <Pressable
              style={[styles.tab, mode === "register" && styles.tabActive]}
              onPress={() => switchMode("register")}
            >
              <Text style={[styles.tabText, mode === "register" && styles.tabTextActive]}>Cadastro</Text>
            </Pressable>
          </View>

          <View style={styles.form}>
            {isRegister && (
              <Field
                label="Nome"
                value={form.name}
                onChangeText={(value) => updateForm("name", value)}
                autoCapitalize="words"
              />
            )}
            <Field
              label="E-mail"
              value={form.email}
              onChangeText={(value) => updateForm("email", value)}
              autoCapitalize="none"
              keyboardType="email-address"
            />
            <Field
              label="Senha"
              value={form.password}
              onChangeText={(value) => updateForm("password", value)}
              secureTextEntry
            />

            <Pressable
              style={[styles.primaryButton, (!canSubmit || submitting) && styles.primaryButtonDisabled]}
              onPress={submit}
              disabled={!canSubmit || submitting}
            >
              {submitting ? (
                <ActivityIndicator color="#102018" />
              ) : (
                <Text style={styles.primaryButtonText}>{isRegister ? "Criar e entrar" : "Entrar"}</Text>
              )}
            </Pressable>
          </View>

          {!!message && (
            <View style={[styles.messageBox, user ? styles.messageSuccess : styles.messageError]}>
              <Text style={styles.messageText}>{message}</Text>
            </View>
          )}

          {user && (
            <View style={styles.profile}>
              <Text style={styles.profileTitle}>Usuário autenticado</Text>
              <Text style={styles.profileLine}>{user.name}</Text>
              <Text style={styles.profileMuted}>{user.email}</Text>
              <Text style={styles.profileMuted}>Plano: {user.plan}</Text>
              <Text style={styles.tokenLabel}>Token JWT</Text>
              <Text style={styles.tokenValue} numberOfLines={3}>
                {token}
              </Text>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Field({ label, ...props }) {
  return (
    <View style={styles.field}>
      <Text style={styles.inputLabel}>{label}</Text>
      <TextInput
        placeholderTextColor="#7d8f87"
        style={styles.input}
        selectionColor="#64e6a2"
        {...props}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#0f1412",
  },
  keyboard: {
    flex: 1,
  },
  content: {
    flexGrow: 1,
    padding: 20,
    gap: 18,
  },
  header: {
    paddingTop: 24,
    gap: 8,
  },
  title: {
    color: "#f4fff9",
    fontSize: 38,
    fontWeight: "800",
  },
  subtitle: {
    color: "#aab9b2",
    fontSize: 16,
    lineHeight: 22,
  },
  statusPanel: {
    alignItems: "center",
    backgroundColor: "#16201c",
    borderColor: "#284239",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    padding: 16,
  },
  label: {
    color: "#64e6a2",
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  statusText: {
    color: "#f4fff9",
    fontSize: 22,
    fontWeight: "800",
    marginTop: 4,
  },
  statusHint: {
    color: "#aab9b2",
    fontSize: 14,
    marginTop: 4,
  },
  iconButton: {
    alignItems: "center",
    backgroundColor: "#21382f",
    borderRadius: 8,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  iconText: {
    color: "#e8fff6",
    fontSize: 22,
    fontWeight: "700",
  },
  tabs: {
    backgroundColor: "#151c19",
    borderRadius: 8,
    flexDirection: "row",
    padding: 4,
  },
  tab: {
    alignItems: "center",
    borderRadius: 6,
    flex: 1,
    paddingVertical: 12,
  },
  tabActive: {
    backgroundColor: "#64e6a2",
  },
  tabText: {
    color: "#aab9b2",
    fontSize: 15,
    fontWeight: "700",
  },
  tabTextActive: {
    color: "#102018",
  },
  form: {
    gap: 14,
  },
  field: {
    gap: 6,
  },
  inputLabel: {
    color: "#d8e8df",
    fontSize: 14,
    fontWeight: "700",
  },
  input: {
    backgroundColor: "#151c19",
    borderColor: "#2d3f38",
    borderRadius: 8,
    borderWidth: 1,
    color: "#f4fff9",
    fontSize: 16,
    minHeight: 52,
    paddingHorizontal: 14,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#64e6a2",
    borderRadius: 8,
    justifyContent: "center",
    minHeight: 54,
    marginTop: 4,
  },
  primaryButtonDisabled: {
    opacity: 0.55,
  },
  primaryButtonText: {
    color: "#102018",
    fontSize: 16,
    fontWeight: "800",
  },
  messageBox: {
    borderRadius: 8,
    padding: 14,
  },
  messageSuccess: {
    backgroundColor: "#173526",
  },
  messageError: {
    backgroundColor: "#3a1f23",
  },
  messageText: {
    color: "#f4fff9",
    fontSize: 14,
    lineHeight: 20,
  },
  profile: {
    backgroundColor: "#16201c",
    borderColor: "#284239",
    borderRadius: 8,
    borderWidth: 1,
    gap: 8,
    padding: 16,
  },
  profileTitle: {
    color: "#64e6a2",
    fontSize: 13,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  profileLine: {
    color: "#f4fff9",
    fontSize: 20,
    fontWeight: "800",
  },
  profileMuted: {
    color: "#aab9b2",
    fontSize: 14,
  },
  tokenLabel: {
    color: "#d8e8df",
    fontSize: 13,
    fontWeight: "800",
    marginTop: 8,
  },
  tokenValue: {
    color: "#aab9b2",
    fontSize: 12,
    lineHeight: 18,
  },
});

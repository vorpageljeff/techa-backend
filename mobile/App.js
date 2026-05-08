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

const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL || "https://techa-backend.onrender.com";

const SAMPLE_POLYGON = {
  type: "Polygon",
  coordinates: [
    [
      [-57.64, -25.31],
      [-57.62, -25.31],
      [-57.62, -25.29],
      [-57.64, -25.29],
      [-57.64, -25.31],
    ],
  ],
};

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

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
  const [token, setToken] = useState("");
  const [user, setUser] = useState(null);
  const [screen, setScreen] = useState("dashboard");
  const [authMode, setAuthMode] = useState("register");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [farms, setFarms] = useState([]);
  const [fieldsByFarm, setFieldsByFarm] = useState({});
  const [anomalies, setAnomalies] = useState([]);
  const [authForm, setAuthForm] = useState({
    name: "Jefferson Teste",
    email: `teste-${Date.now()}@techa.app`,
    password: "123456",
  });
  const [farmForm, setFarmForm] = useState({
    name: "Fazenda Demo",
    crop: "Soja",
    city: "Asuncion",
    state: "Central",
    area_ha: "120",
  });
  const [fieldForm, setFieldForm] = useState({
    farm_id: "",
    name: "Talhao 01",
    crop: "Soja",
    planting_date: new Date().toISOString().slice(0, 10),
  });

  const isLoggedIn = Boolean(token && user);
  const selectedFarmId = fieldForm.farm_id || farms[0]?.id || "";
  const allFields = useMemo(
    () => Object.values(fieldsByFarm).flat(),
    [fieldsByFarm]
  );

  async function loadHealth() {
    try {
      const nextHealth = await apiRequest("/health");
      setHealth(nextHealth);
    } catch (error) {
      setHealth({ status: "error", database: "unknown", message: error.message });
    }
  }

  async function loadAppData(nextToken = token) {
    if (!nextToken) return;
    setLoading(true);
    try {
      const [nextDashboard, nextFarms, nextAnomalies] = await Promise.all([
        apiRequest("/api/v1/dashboard", { token: nextToken }),
        apiRequest("/api/v1/farms", { token: nextToken }),
        apiRequest("/api/v1/anomalies", { token: nextToken }),
      ]);

      setDashboard(nextDashboard);
      setFarms(nextFarms);
      setAnomalies(nextAnomalies);

      const fieldEntries = await Promise.all(
        nextFarms.map(async (farm) => [
          farm.id,
          await apiRequest(`/api/v1/farms/${farm.id}/fields`, { token: nextToken }),
        ])
      );
      setFieldsByFarm(Object.fromEntries(fieldEntries));

      if (!fieldForm.farm_id && nextFarms[0]?.id) {
        setFieldForm((current) => ({ ...current, farm_id: nextFarms[0].id }));
      }
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitAuth() {
    setBusy(true);
    setMessage("");
    try {
      if (authMode === "register") {
        await apiRequest("/api/v1/auth/register", {
          method: "POST",
          body: JSON.stringify({
            name: authForm.name.trim(),
            email: authForm.email.trim(),
            password: authForm.password,
          }),
        });
      }

      const login = await apiRequest("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: authForm.email.trim(),
          password: authForm.password,
        }),
      });
      const profile = await apiRequest("/api/v1/auth/me", {
        token: login.access_token,
      });

      setToken(login.access_token);
      setUser(profile);
      setMessage(authMode === "register" ? "Conta criada e conectada." : "Login feito.");
      await loadAppData(login.access_token);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function createFarm() {
    setBusy(true);
    setMessage("");
    try {
      const farm = await apiRequest("/api/v1/farms", {
        method: "POST",
        token,
        body: JSON.stringify({
          name: farmForm.name.trim(),
          crop: farmForm.crop.trim() || null,
          city: farmForm.city.trim() || null,
          state: farmForm.state.trim() || null,
          area_ha: farmForm.area_ha ? Number(farmForm.area_ha) : null,
        }),
      });
      setMessage("Fazenda criada.");
      setFieldForm((current) => ({ ...current, farm_id: farm.id }));
      await loadAppData();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function createField() {
    const farmId = selectedFarmId;
    if (!farmId) {
      setMessage("Crie uma fazenda antes de criar talhoes.");
      return;
    }

    setBusy(true);
    setMessage("");
    try {
      await apiRequest(`/api/v1/farms/${farmId}/fields`, {
        method: "POST",
        token,
        body: JSON.stringify({
          name: fieldForm.name.trim(),
          crop: fieldForm.crop.trim() || null,
          planting_date: fieldForm.planting_date || null,
          geometry: SAMPLE_POLYGON,
        }),
      });
      setMessage("Talhao criado com poligono de teste.");
      await loadAppData();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    setToken("");
    setUser(null);
    setDashboard(null);
    setFarms([]);
    setFieldsByFarm({});
    setAnomalies([]);
    setScreen("dashboard");
    setMessage("Sessao encerrada.");
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
          <Header health={health} onRefresh={loadHealth} />

          {!isLoggedIn ? (
            <AuthCard
              mode={authMode}
              setMode={setAuthMode}
              form={authForm}
              setForm={setAuthForm}
              busy={busy}
              onSubmit={submitAuth}
            />
          ) : (
            <>
              <View style={styles.nav}>
                {[
                  ["dashboard", "Painel"],
                  ["farms", "Fazendas"],
                  ["fields", "Talhoes"],
                  ["account", "Conta"],
                ].map(([key, label]) => (
                  <Pressable
                    key={key}
                    style={[styles.navItem, screen === key && styles.navItemActive]}
                    onPress={() => setScreen(key)}
                  >
                    <Text style={[styles.navText, screen === key && styles.navTextActive]}>
                      {label}
                    </Text>
                  </Pressable>
                ))}
              </View>

              <View style={styles.toolbar}>
                <Text style={styles.toolbarText}>
                  {user.name} · {user.plan}
                </Text>
                <Pressable style={styles.secondaryButton} onPress={() => loadAppData()}>
                  <Text style={styles.secondaryButtonText}>
                    {loading ? "Atualizando..." : "Atualizar"}
                  </Text>
                </Pressable>
              </View>

              {screen === "dashboard" && (
                <Dashboard dashboard={dashboard} anomalies={anomalies} fields={allFields} />
              )}
              {screen === "farms" && (
                <Farms
                  farms={farms}
                  form={farmForm}
                  setForm={setFarmForm}
                  busy={busy}
                  onCreate={createFarm}
                />
              )}
              {screen === "fields" && (
                <Fields
                  farms={farms}
                  fieldsByFarm={fieldsByFarm}
                  form={fieldForm}
                  setForm={setFieldForm}
                  busy={busy}
                  onCreate={createField}
                />
              )}
              {screen === "account" && (
                <Account user={user} token={token} apiBaseUrl={API_BASE_URL} onLogout={logout} />
              )}
            </>
          )}

          {!!message && (
            <View style={styles.messageBox}>
              <Text style={styles.messageText}>{message}</Text>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Header({ health, onRefresh }) {
  return (
    <View style={styles.header}>
      <View>
        <Text style={styles.title}>Techa</Text>
        <Text style={styles.subtitle}>Monitoramento agricola com backend em producao</Text>
      </View>
      <View style={styles.statusPanel}>
        <View>
          <Text style={styles.label}>API</Text>
          <Text style={styles.statusText}>{health?.status || "..."}</Text>
          <Text style={styles.statusHint}>Banco: {health?.database || "..."}</Text>
        </View>
        <Pressable style={styles.iconButton} onPress={onRefresh}>
          <Text style={styles.iconText}>R</Text>
        </Pressable>
      </View>
    </View>
  );
}

function AuthCard({ mode, setMode, form, setForm, busy, onSubmit }) {
  const isRegister = mode === "register";
  return (
    <View style={styles.panel}>
      <Segmented
        value={mode}
        onChange={setMode}
        options={[
          ["register", "Cadastro"],
          ["login", "Login"],
        ]}
      />
      {isRegister && (
        <Field
          label="Nome"
          value={form.name}
          onChangeText={(value) => setForm((current) => ({ ...current, name: value }))}
          autoCapitalize="words"
        />
      )}
      <Field
        label="E-mail"
        value={form.email}
        onChangeText={(value) => setForm((current) => ({ ...current, email: value }))}
        autoCapitalize="none"
        keyboardType="email-address"
      />
      <Field
        label="Senha"
        value={form.password}
        onChangeText={(value) => setForm((current) => ({ ...current, password: value }))}
        secureTextEntry
      />
      <PrimaryButton
        label={isRegister ? "Criar conta e entrar" : "Entrar"}
        busy={busy}
        onPress={onSubmit}
      />
    </View>
  );
}

function Dashboard({ dashboard, anomalies, fields }) {
  return (
    <View style={styles.stack}>
      <View style={styles.metricsGrid}>
        <Metric label="Fazendas" value={dashboard?.farms_count ?? 0} />
        <Metric label="Talhoes" value={dashboard?.fields_count ?? 0} />
        <Metric label="Area total" value={`${dashboard?.total_area_ha ?? 0} ha`} />
        <Metric label="Alertas" value={dashboard?.active_anomalies ?? 0} />
      </View>

      <Section title="Talhoes monitorados">
        {fields.length === 0 ? (
          <Empty text="Crie uma fazenda e um talhao para popular o painel." />
        ) : (
          fields.map((field) => (
            <ListItem
              key={field.id}
              title={field.name}
              subtitle={`${field.crop || "Cultura nao informada"} · ${formatArea(field.area_ha)}`}
              right={field.planting_date || "sem plantio"}
            />
          ))
        )}
      </Section>

      <Section title="Anomalias recentes">
        {anomalies.length === 0 ? (
          <Empty text="Nenhuma anomalia registrada ate agora." />
        ) : (
          anomalies.slice(0, 5).map((anomaly) => (
            <ListItem
              key={anomaly.id}
              title={anomaly.suspected_type}
              subtitle={`${formatArea(anomaly.affected_area_ha)} afetados`}
              right={anomaly.status}
            />
          ))
        )}
      </Section>
    </View>
  );
}

function Farms({ farms, form, setForm, busy, onCreate }) {
  return (
    <View style={styles.stack}>
      <Section title="Nova fazenda">
        <Field
          label="Nome"
          value={form.name}
          onChangeText={(value) => setForm((current) => ({ ...current, name: value }))}
        />
        <View style={styles.twoColumns}>
          <Field
            label="Cultura"
            value={form.crop}
            onChangeText={(value) => setForm((current) => ({ ...current, crop: value }))}
          />
          <Field
            label="Area ha"
            value={form.area_ha}
            onChangeText={(value) => setForm((current) => ({ ...current, area_ha: value }))}
            keyboardType="numeric"
          />
        </View>
        <View style={styles.twoColumns}>
          <Field
            label="Cidade"
            value={form.city}
            onChangeText={(value) => setForm((current) => ({ ...current, city: value }))}
          />
          <Field
            label="Estado"
            value={form.state}
            onChangeText={(value) => setForm((current) => ({ ...current, state: value }))}
          />
        </View>
        <PrimaryButton label="Criar fazenda" busy={busy} onPress={onCreate} />
      </Section>

      <Section title="Fazendas cadastradas">
        {farms.length === 0 ? (
          <Empty text="Voce ainda nao tem fazendas cadastradas." />
        ) : (
          farms.map((farm) => (
            <ListItem
              key={farm.id}
              title={farm.name}
              subtitle={`${farm.crop || "Sem cultura"} · ${farm.city || "Sem cidade"}`}
              right={formatArea(farm.area_ha)}
            />
          ))
        )}
      </Section>
    </View>
  );
}

function Fields({ farms, fieldsByFarm, form, setForm, busy, onCreate }) {
  const selectedFarm = form.farm_id || farms[0]?.id || "";
  const fields = selectedFarm ? fieldsByFarm[selectedFarm] || [] : [];

  return (
    <View style={styles.stack}>
      <Section title="Novo talhao">
        <Text style={styles.inputLabel}>Fazenda</Text>
        <View style={styles.chips}>
          {farms.length === 0 ? (
            <Text style={styles.muted}>Crie uma fazenda primeiro.</Text>
          ) : (
            farms.map((farm) => (
              <Pressable
                key={farm.id}
                style={[styles.chip, selectedFarm === farm.id && styles.chipActive]}
                onPress={() => setForm((current) => ({ ...current, farm_id: farm.id }))}
              >
                <Text style={[styles.chipText, selectedFarm === farm.id && styles.chipTextActive]}>
                  {farm.name}
                </Text>
              </Pressable>
            ))
          )}
        </View>
        <Field
          label="Nome"
          value={form.name}
          onChangeText={(value) => setForm((current) => ({ ...current, name: value }))}
        />
        <View style={styles.twoColumns}>
          <Field
            label="Cultura"
            value={form.crop}
            onChangeText={(value) => setForm((current) => ({ ...current, crop: value }))}
          />
          <Field
            label="Plantio"
            value={form.planting_date}
            onChangeText={(value) => setForm((current) => ({ ...current, planting_date: value }))}
          />
        </View>
        <Text style={styles.helperText}>
          O MVP usa um poligono de teste perto de Assuncao. Depois a gente troca por desenho no mapa.
        </Text>
        <PrimaryButton label="Criar talhao" busy={busy} onPress={onCreate} />
      </Section>

      <Section title="Talhoes da fazenda">
        {fields.length === 0 ? (
          <Empty text="Nenhum talhao cadastrado nessa fazenda." />
        ) : (
          fields.map((field) => (
            <ListItem
              key={field.id}
              title={field.name}
              subtitle={`${field.crop || "Sem cultura"} · ${formatArea(field.area_ha)}`}
              right={field.planting_date || "sem data"}
            />
          ))
        )}
      </Section>
    </View>
  );
}

function Account({ user, token, apiBaseUrl, onLogout }) {
  return (
    <View style={styles.stack}>
      <Section title="Conta">
        <ListItem title={user.name} subtitle={user.email} right={user.plan} />
        <Text style={styles.tokenLabel}>API</Text>
        <Text style={styles.code}>{apiBaseUrl}</Text>
        <Text style={styles.tokenLabel}>Token JWT</Text>
        <Text style={styles.code} numberOfLines={4}>
          {token}
        </Text>
        <Pressable style={styles.dangerButton} onPress={onLogout}>
          <Text style={styles.dangerButtonText}>Sair</Text>
        </Pressable>
      </Section>
    </View>
  );
}

function Section({ title, children }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.sectionBody}>{children}</View>
    </View>
  );
}

function Metric({ label, value }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function ListItem({ title, subtitle, right }) {
  return (
    <View style={styles.listItem}>
      <View style={styles.listMain}>
        <Text style={styles.listTitle}>{title}</Text>
        <Text style={styles.listSubtitle}>{subtitle}</Text>
      </View>
      <Text style={styles.listRight}>{right}</Text>
    </View>
  );
}

function Empty({ text }) {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyText}>{text}</Text>
    </View>
  );
}

function Segmented({ value, onChange, options }) {
  return (
    <View style={styles.segmented}>
      {options.map(([key, label]) => (
        <Pressable
          key={key}
          style={[styles.segment, value === key && styles.segmentActive]}
          onPress={() => onChange(key)}
        >
          <Text style={[styles.segmentText, value === key && styles.segmentTextActive]}>
            {label}
          </Text>
        </Pressable>
      ))}
    </View>
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

function PrimaryButton({ label, busy, onPress }) {
  return (
    <Pressable style={[styles.primaryButton, busy && styles.disabled]} onPress={onPress} disabled={busy}>
      {busy ? <ActivityIndicator color="#102018" /> : <Text style={styles.primaryButtonText}>{label}</Text>}
    </Pressable>
  );
}

function formatArea(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "0 ha";
  return `${Number(value).toFixed(1)} ha`;
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
    gap: 18,
    padding: 20,
    width: "100%",
  },
  header: {
    gap: 18,
    paddingTop: 18,
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
    fontWeight: "800",
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
    fontSize: 18,
    fontWeight: "800",
  },
  panel: {
    backgroundColor: "#16201c",
    borderColor: "#284239",
    borderRadius: 8,
    borderWidth: 1,
    gap: 14,
    padding: 16,
  },
  segmented: {
    backgroundColor: "#111916",
    borderRadius: 8,
    flexDirection: "row",
    padding: 4,
  },
  segment: {
    alignItems: "center",
    borderRadius: 6,
    flex: 1,
    paddingVertical: 12,
  },
  segmentActive: {
    backgroundColor: "#64e6a2",
  },
  segmentText: {
    color: "#aab9b2",
    fontSize: 15,
    fontWeight: "800",
  },
  segmentTextActive: {
    color: "#102018",
  },
  nav: {
    backgroundColor: "#151c19",
    borderRadius: 8,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    padding: 4,
  },
  navItem: {
    alignItems: "center",
    borderRadius: 6,
    flexGrow: 1,
    minWidth: 86,
    paddingVertical: 11,
  },
  navItemActive: {
    backgroundColor: "#64e6a2",
  },
  navText: {
    color: "#aab9b2",
    fontSize: 14,
    fontWeight: "800",
  },
  navTextActive: {
    color: "#102018",
  },
  toolbar: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
  },
  toolbarText: {
    color: "#d8e8df",
    flex: 1,
    fontSize: 14,
    fontWeight: "700",
  },
  stack: {
    gap: 16,
  },
  metricsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  metric: {
    backgroundColor: "#16201c",
    borderColor: "#284239",
    borderRadius: 8,
    borderWidth: 1,
    flexBasis: "48%",
    flexGrow: 1,
    minWidth: 145,
    padding: 14,
  },
  metricLabel: {
    color: "#64e6a2",
    fontSize: 12,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  metricValue: {
    color: "#f4fff9",
    fontSize: 24,
    fontWeight: "800",
    marginTop: 6,
  },
  section: {
    backgroundColor: "#16201c",
    borderColor: "#284239",
    borderRadius: 8,
    borderWidth: 1,
    padding: 16,
  },
  sectionTitle: {
    color: "#f4fff9",
    fontSize: 18,
    fontWeight: "800",
    marginBottom: 14,
  },
  sectionBody: {
    gap: 12,
  },
  field: {
    flex: 1,
    gap: 6,
    minWidth: 135,
  },
  inputLabel: {
    color: "#d8e8df",
    fontSize: 14,
    fontWeight: "800",
  },
  input: {
    backgroundColor: "#111916",
    borderColor: "#2d3f38",
    borderRadius: 8,
    borderWidth: 1,
    color: "#f4fff9",
    fontSize: 16,
    minHeight: 52,
    paddingHorizontal: 14,
  },
  twoColumns: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#64e6a2",
    borderRadius: 8,
    justifyContent: "center",
    minHeight: 54,
  },
  primaryButtonText: {
    color: "#102018",
    fontSize: 16,
    fontWeight: "800",
  },
  secondaryButton: {
    backgroundColor: "#21382f",
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  secondaryButtonText: {
    color: "#e8fff6",
    fontSize: 13,
    fontWeight: "800",
  },
  dangerButton: {
    alignItems: "center",
    backgroundColor: "#3a1f23",
    borderRadius: 8,
    minHeight: 48,
    justifyContent: "center",
  },
  dangerButtonText: {
    color: "#ffd7dd",
    fontSize: 15,
    fontWeight: "800",
  },
  disabled: {
    opacity: 0.55,
  },
  listItem: {
    alignItems: "center",
    backgroundColor: "#111916",
    borderColor: "#263931",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
    padding: 14,
  },
  listMain: {
    flex: 1,
    gap: 4,
  },
  listTitle: {
    color: "#f4fff9",
    fontSize: 16,
    fontWeight: "800",
  },
  listSubtitle: {
    color: "#aab9b2",
    fontSize: 13,
  },
  listRight: {
    color: "#64e6a2",
    fontSize: 13,
    fontWeight: "800",
    maxWidth: 120,
    textAlign: "right",
  },
  empty: {
    backgroundColor: "#111916",
    borderRadius: 8,
    padding: 14,
  },
  emptyText: {
    color: "#aab9b2",
    fontSize: 14,
    lineHeight: 20,
  },
  chips: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  chip: {
    backgroundColor: "#111916",
    borderColor: "#2d3f38",
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  chipActive: {
    backgroundColor: "#64e6a2",
    borderColor: "#64e6a2",
  },
  chipText: {
    color: "#d8e8df",
    fontSize: 13,
    fontWeight: "800",
  },
  chipTextActive: {
    color: "#102018",
  },
  helperText: {
    color: "#aab9b2",
    fontSize: 13,
    lineHeight: 19,
  },
  muted: {
    color: "#aab9b2",
    fontSize: 14,
  },
  messageBox: {
    backgroundColor: "#173526",
    borderRadius: 8,
    padding: 14,
  },
  messageText: {
    color: "#f4fff9",
    fontSize: 14,
    lineHeight: 20,
  },
  tokenLabel: {
    color: "#d8e8df",
    fontSize: 13,
    fontWeight: "800",
  },
  code: {
    backgroundColor: "#111916",
    borderRadius: 8,
    color: "#aab9b2",
    fontSize: 12,
    lineHeight: 18,
    padding: 12,
  },
});

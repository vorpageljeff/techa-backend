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
    name: "Talhao 02",
    crop: "Soja",
    planting_date: new Date().toISOString().slice(0, 10),
  });

  const isLoggedIn = Boolean(token && user);
  const selectedFarmId = fieldForm.farm_id || farms[0]?.id || "";
  const allFields = useMemo(() => Object.values(fieldsByFarm).flat(), [fieldsByFarm]);

  async function loadHealth() {
    try {
      setHealth(await apiRequest("/health"));
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
      setScreen("dashboard");
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
        <View style={styles.phone}>
          {!isLoggedIn ? (
            <AuthScreen
              health={health}
              authMode={authMode}
              setAuthMode={setAuthMode}
              form={authForm}
              setForm={setAuthForm}
              busy={busy}
              onSubmit={submitAuth}
              onRefresh={loadHealth}
              message={message}
            />
          ) : (
            <LoggedApp
              screen={screen}
              setScreen={setScreen}
              user={user}
              health={health}
              dashboard={dashboard}
              farms={farms}
              fields={allFields}
              fieldsByFarm={fieldsByFarm}
              anomalies={anomalies}
              loading={loading}
              farmForm={farmForm}
              setFarmForm={setFarmForm}
              fieldForm={fieldForm}
              setFieldForm={setFieldForm}
              busy={busy}
              message={message}
              onRefresh={() => loadAppData()}
              onCreateFarm={createFarm}
              onCreateField={createField}
              onLogout={logout}
            />
          )}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function AuthScreen({
  health,
  authMode,
  setAuthMode,
  form,
  setForm,
  busy,
  onSubmit,
  onRefresh,
  message,
}) {
  const isRegister = authMode === "register";

  return (
    <ScrollView contentContainerStyle={styles.authContent} keyboardShouldPersistTaps="handled">
      <BrandHeader compact={false} />
      <View style={styles.apiStrip}>
        <View>
          <Text style={styles.apiLabel}>API</Text>
          <Text style={styles.apiStatus}>{health?.status || "..."}</Text>
          <Text style={styles.apiHint}>Banco: {health?.database || "..."}</Text>
        </View>
        <Pressable style={styles.refreshButton} onPress={onRefresh}>
          <Text style={styles.refreshText}>R</Text>
        </Pressable>
      </View>

      <View style={styles.loginPanel}>
        <Text style={styles.loginTitle}>{isRegister ? "Configuracao Inicial" : "Login"}</Text>
        <ModeSwitch value={authMode} onChange={setAuthMode} />
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
        <Pressable style={styles.roundAction} onPress={onSubmit} disabled={busy}>
          {busy ? (
            <ActivityIndicator color="#ffffff" />
          ) : (
            <Text style={styles.roundActionText}>
              {isRegister ? "Cadastrar\nFazenda" : "Entrar"}
            </Text>
          )}
        </Pressable>
        <View style={styles.welcomeBox}>
          <Text style={styles.welcomeTitle}>BEM-VINDO.</Text>
          <Text style={styles.welcomeText}>Gerando mapa de vigor inicial (NDVI).</Text>
        </View>
      </View>
      {!!message && <Message text={message} />}
    </ScrollView>
  );
}

function LoggedApp(props) {
  return (
    <View style={styles.logged}>
      <BrandHeader compact />
      {props.screen === "dashboard" && (
        <DashboardScreen
          dashboard={props.dashboard}
          fields={props.fields}
          anomalies={props.anomalies}
          loading={props.loading}
          onRefresh={props.onRefresh}
          setScreen={props.setScreen}
        />
      )}
      {props.screen === "setup" && (
        <SetupScreen
          farms={props.farms}
          fieldsByFarm={props.fieldsByFarm}
          farmForm={props.farmForm}
          setFarmForm={props.setFarmForm}
          fieldForm={props.fieldForm}
          setFieldForm={props.setFieldForm}
          busy={props.busy}
          onCreateFarm={props.onCreateFarm}
          onCreateField={props.onCreateField}
        />
      )}
      {props.screen === "inspection" && (
        <InspectionScreen fields={props.fields} anomalies={props.anomalies} />
      )}
      {props.screen === "account" && (
        <AccountScreen user={props.user} onLogout={props.onLogout} />
      )}
      {!!props.message && <Message text={props.message} />}
      <BottomNav value={props.screen} onChange={props.setScreen} />
    </View>
  );
}

function DashboardScreen({ dashboard, fields, anomalies, loading, onRefresh, setScreen }) {
  const alertCount = dashboard?.active_anomalies ?? anomalies.length;
  const fieldName = fields[0]?.name || "Talhao 02";

  return (
    <ScrollView contentContainerStyle={styles.appContent}>
      <View style={styles.offlineBanner}>
        <Text style={styles.offlineIcon}>!</Text>
        <Text style={styles.offlineText}>MODO OFFLINE ATIVO</Text>
        <Text style={styles.bell}>●</Text>
      </View>
      <Text style={styles.pageTitle}>Dashboard</Text>

      <View style={styles.mapCard}>
        <FieldMap alertCount={alertCount} />
        <View style={styles.alertBubble}>
          <Text style={styles.alertMark}>!</Text>
          <Text style={styles.alertText}>DETECTADA VARIACAO{"\n"}NO {fieldName.toUpperCase()}</Text>
        </View>
        <Pressable style={styles.navToAnomaly} onPress={() => setScreen("inspection")}>
          <Text style={styles.navToAnomalyText}>Navegar para{"\n"}Anomalia</Text>
        </Pressable>
      </View>

      <View style={styles.problemPanel}>
        <Text style={styles.problemTitle}>PROBLEMAS INTERPRETADOS:</Text>
        <View style={styles.problemRow}>
          <Problem label="Estresse\nHidrico" icon="☁" />
          <Problem label="Deficiencia\nNutricional" icon="◒" />
          <Problem label="Ataque de\nPragas" icon="!" />
        </View>
      </View>

      <View style={styles.metricsRow}>
        <Metric label="Fazendas" value={dashboard?.farms_count ?? 0} />
        <Metric label="Talhoes" value={dashboard?.fields_count ?? fields.length} />
        <Metric label="Alertas" value={alertCount} />
      </View>

      <Pressable style={styles.actionButton} onPress={onRefresh}>
        <Text style={styles.actionButtonText}>{loading ? "Atualizando..." : "Atualizar dados"}</Text>
      </Pressable>
    </ScrollView>
  );
}

function SetupScreen({
  farms,
  fieldsByFarm,
  farmForm,
  setFarmForm,
  fieldForm,
  setFieldForm,
  busy,
  onCreateFarm,
  onCreateField,
}) {
  const selectedFarm = fieldForm.farm_id || farms[0]?.id || "";
  const fields = selectedFarm ? fieldsByFarm[selectedFarm] || [] : [];

  return (
    <ScrollView contentContainerStyle={styles.appContent}>
      <Text style={styles.pageTitle}>Configurar Fazenda</Text>
      <View style={styles.formPanel}>
        <Field
          label="Nome da fazenda"
          value={farmForm.name}
          onChangeText={(value) => setFarmForm((current) => ({ ...current, name: value }))}
        />
        <View style={styles.inlineFields}>
          <Field
            label="Cultura"
            value={farmForm.crop}
            onChangeText={(value) => setFarmForm((current) => ({ ...current, crop: value }))}
          />
          <Field
            label="Area ha"
            value={farmForm.area_ha}
            onChangeText={(value) => setFarmForm((current) => ({ ...current, area_ha: value }))}
            keyboardType="numeric"
          />
        </View>
        <Pressable style={styles.actionButton} onPress={onCreateFarm} disabled={busy}>
          <Text style={styles.actionButtonText}>Cadastrar Fazenda</Text>
        </Pressable>
      </View>

      <View style={styles.formPanel}>
        <Text style={styles.panelTitle}>Mapear Talhoes</Text>
        <View style={styles.chips}>
          {farms.length === 0 ? (
            <Text style={styles.muted}>Cadastre uma fazenda primeiro.</Text>
          ) : (
            farms.map((farm) => (
              <Pressable
                key={farm.id}
                style={[styles.chip, selectedFarm === farm.id && styles.chipActive]}
                onPress={() => setFieldForm((current) => ({ ...current, farm_id: farm.id }))}
              >
                <Text style={[styles.chipText, selectedFarm === farm.id && styles.chipTextActive]}>
                  {farm.name}
                </Text>
              </Pressable>
            ))
          )}
        </View>
        <Field
          label="Nome do talhao"
          value={fieldForm.name}
          onChangeText={(value) => setFieldForm((current) => ({ ...current, name: value }))}
        />
        <Pressable style={styles.actionButton} onPress={onCreateField} disabled={busy}>
          <Text style={styles.actionButtonText}>Gerar mapa de vigor inicial</Text>
        </Pressable>
        <Text style={styles.smallNote}>Talhoes nesta fazenda: {fields.length}</Text>
      </View>
    </ScrollView>
  );
}

function InspectionScreen({ fields, anomalies }) {
  return (
    <ScrollView contentContainerStyle={styles.appContent}>
      <Text style={styles.pageTitle}>Inspecao de Campo</Text>
      <View style={styles.inspectionMap}>
        <View style={styles.satellitePatchA} />
        <View style={styles.satellitePatchB} />
        <View style={styles.routeOne} />
        <View style={styles.routeTwo} />
        <View style={styles.bluePin} />
        <View style={styles.notePin}>
          <Text style={styles.notePinText}>□</Text>
        </View>
      </View>
      <View style={styles.inspectionActions}>
        <Pressable style={styles.bigRound}>
          <Text style={styles.bigRoundIcon}>CAM</Text>
          <Text style={styles.bigRoundText}>REGISTRAR{"\n"}INSPECAO</Text>
        </Pressable>
        <Pressable style={styles.bigRound}>
          <Text style={styles.bigRoundText}>REGISTRAR{"\n"}NOTAS</Text>
        </Pressable>
      </View>
      <View style={styles.syncPanel}>
        <Text style={styles.syncText}>Dados salvos localmente. Sincronizacao pendente.</Text>
        <View style={styles.progressTrack}>
          <View style={styles.progressFill} />
        </View>
      </View>
      <Text style={styles.smallNote}>
        Talhoes: {fields.length} · Alertas: {anomalies.length}
      </Text>
    </ScrollView>
  );
}

function AccountScreen({ user, onLogout }) {
  return (
    <ScrollView contentContainerStyle={styles.appContent}>
      <Text style={styles.pageTitle}>Conta</Text>
      <View style={styles.formPanel}>
        <Text style={styles.panelTitle}>{user.name}</Text>
        <Text style={styles.muted}>{user.email}</Text>
        <Text style={styles.muted}>Plano: {user.plan}</Text>
        <Pressable style={styles.logoutButton} onPress={onLogout}>
          <Text style={styles.logoutButtonText}>Sair</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

function BrandHeader({ compact }) {
  return (
    <View style={[styles.brandHeader, compact && styles.brandHeaderCompact]}>
      <Logo />
      <View>
        <Text style={styles.brandTitle}>Techa</Text>
        <Text style={styles.brandSubtitle}>by InnovAgro Py</Text>
      </View>
    </View>
  );
}

function Logo() {
  return (
    <View style={styles.logo}>
      <View style={styles.logoSun} />
      <View style={styles.logoLeafOne} />
      <View style={styles.logoLeafTwo} />
      <View style={styles.logoLeafThree} />
    </View>
  );
}

function ModeSwitch({ value, onChange }) {
  return (
    <View style={styles.modeSwitch}>
      {[
        ["register", "Cadastro"],
        ["login", "Login"],
      ].map(([key, label]) => (
        <Pressable
          key={key}
          style={[styles.modeButton, value === key && styles.modeButtonActive]}
          onPress={() => onChange(key)}
        >
          <Text style={[styles.modeText, value === key && styles.modeTextActive]}>{label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function BottomNav({ value, onChange }) {
  const items = [
    ["dashboard", "Mapa"],
    ["setup", "Config"],
    ["inspection", "Campo"],
    ["account", "Conta"],
  ];

  return (
    <View style={styles.bottomNav}>
      {items.map(([key, label]) => (
        <Pressable key={key} style={styles.bottomItem} onPress={() => onChange(key)}>
          <View style={[styles.bottomDot, value === key && styles.bottomDotActive]} />
          <Text style={[styles.bottomText, value === key && styles.bottomTextActive]}>{label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function FieldMap({ alertCount }) {
  return (
    <View style={styles.fieldMap}>
      <View style={styles.mapRoadOne} />
      <View style={styles.mapRoadTwo} />
      <View style={styles.fieldShape}>
        <View style={styles.ndviGreen} />
        <View style={styles.ndviYellow} />
        <View style={styles.ndviRed} />
        <View style={styles.ndviRedTwo} />
        <View style={styles.alertPinOne}>
          <Text style={styles.pinText}>!</Text>
        </View>
        <View style={styles.alertPinTwo}>
          <Text style={styles.pinText}>!</Text>
        </View>
      </View>
      <Text style={styles.mapTag}>{alertCount > 0 ? `${alertCount} alerta(s)` : "sem alertas reais"}</Text>
    </View>
  );
}

function Problem({ label, icon }) {
  return (
    <View style={styles.problemItem}>
      <Text style={styles.problemIcon}>{icon}</Text>
      <Text style={styles.problemLabel}>{label}</Text>
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

function Field({ label, ...props }) {
  return (
    <View style={styles.field}>
      <Text style={styles.inputLabel}>{label}</Text>
      <TextInput placeholderTextColor="#8a8a8a" style={styles.input} {...props} />
    </View>
  );
}

function Message({ text }) {
  return (
    <View style={styles.messageBox}>
      <Text style={styles.messageText}>{text}</Text>
    </View>
  );
}

const NAVY = "#09294a";
const NAVY_DARK = "#061d36";
const GREEN = "#2f7b3d";
const GREEN_LIGHT = "#7bbd54";
const CREAM = "#f5f1d7";
const RED = "#cf2f24";
const TEXT = "#102033";

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#dfeef4",
  },
  keyboard: {
    flex: 1,
  },
  phone: {
    flex: 1,
    backgroundColor: "#eef4f0",
  },
  authContent: {
    backgroundColor: "#ffffff",
    flexGrow: 1,
    paddingBottom: 28,
  },
  logged: {
    backgroundColor: "#eef4f0",
    flex: 1,
  },
  brandHeader: {
    alignItems: "center",
    backgroundColor: NAVY,
    flexDirection: "row",
    justifyContent: "center",
    minHeight: 92,
    paddingHorizontal: 18,
    paddingTop: 12,
  },
  brandHeaderCompact: {
    minHeight: 78,
  },
  brandTitle: {
    color: "#ffffff",
    fontSize: 30,
    fontWeight: "800",
    letterSpacing: 0,
  },
  brandSubtitle: {
    color: "#d8e6f2",
    fontSize: 13,
    fontWeight: "600",
    marginTop: -2,
  },
  logo: {
    backgroundColor: "#f7f3da",
    borderRadius: 23,
    height: 46,
    marginRight: 10,
    overflow: "hidden",
    position: "relative",
    width: 46,
  },
  logoSun: {
    backgroundColor: "#efc64f",
    borderRadius: 18,
    height: 30,
    left: 8,
    position: "absolute",
    top: 2,
    width: 30,
  },
  logoLeafOne: {
    backgroundColor: "#216b3f",
    borderRadius: 20,
    bottom: 0,
    height: 35,
    left: 5,
    position: "absolute",
    transform: [{ rotate: "26deg" }],
    width: 15,
  },
  logoLeafTwo: {
    backgroundColor: "#2f8b49",
    borderRadius: 20,
    bottom: -2,
    height: 40,
    left: 18,
    position: "absolute",
    transform: [{ rotate: "22deg" }],
    width: 12,
  },
  logoLeafThree: {
    backgroundColor: "#143a5f",
    borderRadius: 20,
    bottom: 0,
    height: 34,
    left: 30,
    position: "absolute",
    transform: [{ rotate: "24deg" }],
    width: 9,
  },
  apiStrip: {
    alignItems: "center",
    backgroundColor: "#e7f0e7",
    borderColor: "#bfd0bf",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    margin: 18,
    padding: 14,
  },
  apiLabel: {
    color: GREEN,
    fontSize: 13,
    fontWeight: "800",
  },
  apiStatus: {
    color: TEXT,
    fontSize: 26,
    fontWeight: "800",
    marginTop: 2,
  },
  apiHint: {
    color: "#57645c",
    fontSize: 14,
  },
  refreshButton: {
    alignItems: "center",
    backgroundColor: NAVY,
    borderRadius: 38,
    height: 58,
    justifyContent: "center",
    width: 58,
  },
  refreshText: {
    color: "#ffffff",
    fontSize: 24,
    fontWeight: "800",
  },
  loginPanel: {
    backgroundColor: "#ffffff",
    paddingHorizontal: 24,
  },
  loginTitle: {
    color: TEXT,
    fontSize: 32,
    fontWeight: "800",
    marginBottom: 16,
    marginTop: 8,
    textAlign: "center",
  },
  modeSwitch: {
    alignSelf: "center",
    backgroundColor: "#eef1ed",
    borderRadius: 8,
    flexDirection: "row",
    marginBottom: 18,
    padding: 4,
    width: "100%",
  },
  modeButton: {
    alignItems: "center",
    borderRadius: 6,
    flex: 1,
    paddingVertical: 11,
  },
  modeButtonActive: {
    backgroundColor: NAVY,
  },
  modeText: {
    color: "#5b635d",
    fontSize: 16,
    fontWeight: "800",
  },
  modeTextActive: {
    color: "#ffffff",
  },
  field: {
    gap: 6,
    marginBottom: 14,
  },
  inputLabel: {
    color: "#202020",
    fontSize: 17,
    fontWeight: "700",
  },
  input: {
    backgroundColor: "#ffffff",
    borderColor: "#2a2a2a",
    borderRadius: 7,
    borderWidth: 1.5,
    color: "#111111",
    fontSize: 18,
    minHeight: 48,
    paddingHorizontal: 12,
  },
  roundAction: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: NAVY,
    borderColor: "#bfd2e8",
    borderRadius: 78,
    borderWidth: 4,
    height: 156,
    justifyContent: "center",
    marginVertical: 18,
    width: 156,
  },
  roundActionText: {
    color: "#ffffff",
    fontSize: 23,
    fontWeight: "800",
    lineHeight: 29,
    textAlign: "center",
  },
  welcomeBox: {
    backgroundColor: CREAM,
    borderColor: "#d9dcc1",
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 16,
  },
  welcomeTitle: {
    color: TEXT,
    fontSize: 18,
    fontWeight: "800",
  },
  welcomeText: {
    color: "#1d2d22",
    fontSize: 16,
    marginTop: 4,
  },
  appContent: {
    paddingBottom: 104,
  },
  offlineBanner: {
    alignItems: "center",
    backgroundColor: NAVY_DARK,
    flexDirection: "row",
    justifyContent: "center",
    minHeight: 54,
    paddingHorizontal: 16,
  },
  offlineIcon: {
    color: RED,
    fontSize: 30,
    fontWeight: "900",
    marginRight: 10,
  },
  offlineText: {
    color: "#ffffff",
    flex: 1,
    fontSize: 19,
    fontWeight: "900",
    textAlign: "center",
  },
  bell: {
    color: RED,
    fontSize: 28,
  },
  pageTitle: {
    color: TEXT,
    fontSize: 30,
    fontWeight: "900",
    paddingHorizontal: 18,
    paddingVertical: 14,
    textAlign: "center",
  },
  mapCard: {
    backgroundColor: "#d5e5c1",
    height: 420,
    marginHorizontal: 18,
    overflow: "hidden",
    position: "relative",
  },
  fieldMap: {
    flex: 1,
    backgroundColor: "#d9e5c8",
    position: "relative",
  },
  mapRoadOne: {
    backgroundColor: "#b9c5a3",
    height: 22,
    left: -30,
    position: "absolute",
    top: 190,
    transform: [{ rotate: "-28deg" }],
    width: 520,
  },
  mapRoadTwo: {
    backgroundColor: "#c4cfad",
    height: 18,
    left: 80,
    position: "absolute",
    top: 40,
    transform: [{ rotate: "38deg" }],
    width: 400,
  },
  fieldShape: {
    backgroundColor: "#5aad4a",
    borderColor: "#0fae2d",
    borderRadius: 8,
    borderWidth: 5,
    height: 285,
    left: 82,
    overflow: "hidden",
    position: "absolute",
    top: 54,
    transform: [{ rotate: "14deg" }],
    width: 230,
  },
  ndviGreen: {
    backgroundColor: "#74c553",
    bottom: 0,
    left: 0,
    position: "absolute",
    top: 0,
    width: 90,
  },
  ndviYellow: {
    backgroundColor: "#d5c34d",
    borderRadius: 80,
    height: 210,
    left: 72,
    position: "absolute",
    top: 24,
    width: 120,
  },
  ndviRed: {
    backgroundColor: "#c9432f",
    borderRadius: 80,
    height: 180,
    left: 118,
    position: "absolute",
    top: 28,
    width: 100,
  },
  ndviRedTwo: {
    backgroundColor: "#d73a31",
    borderRadius: 54,
    height: 86,
    left: 96,
    position: "absolute",
    top: 170,
    width: 88,
  },
  alertPinOne: {
    alignItems: "center",
    backgroundColor: RED,
    borderColor: "#f0b3a6",
    borderRadius: 28,
    borderWidth: 3,
    height: 56,
    justifyContent: "center",
    left: 128,
    position: "absolute",
    top: 92,
    width: 56,
  },
  alertPinTwo: {
    alignItems: "center",
    backgroundColor: RED,
    borderColor: "#f0b3a6",
    borderRadius: 28,
    borderWidth: 3,
    height: 56,
    justifyContent: "center",
    left: 92,
    position: "absolute",
    top: 184,
    width: 56,
  },
  pinText: {
    color: "#ffffff",
    fontSize: 30,
    fontWeight: "900",
  },
  mapTag: {
    backgroundColor: "rgba(255,255,255,0.88)",
    borderRadius: 4,
    bottom: 10,
    color: TEXT,
    fontSize: 14,
    fontWeight: "800",
    left: 12,
    paddingHorizontal: 8,
    paddingVertical: 4,
    position: "absolute",
  },
  alertBubble: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    borderColor: "#2d3d4f",
    borderRadius: 8,
    borderWidth: 2,
    flexDirection: "row",
    left: 142,
    padding: 10,
    position: "absolute",
    top: 44,
    width: 225,
  },
  alertMark: {
    color: RED,
    fontSize: 30,
    fontWeight: "900",
    marginRight: 8,
  },
  alertText: {
    color: TEXT,
    flex: 1,
    fontSize: 15,
    fontWeight: "900",
  },
  navToAnomaly: {
    alignItems: "center",
    backgroundColor: NAVY,
    borderColor: "#b5d7f1",
    borderRadius: 76,
    borderWidth: 4,
    bottom: -16,
    height: 140,
    justifyContent: "center",
    position: "absolute",
    right: 6,
    width: 140,
  },
  navToAnomalyText: {
    color: "#ffffff",
    fontSize: 17,
    fontWeight: "900",
    lineHeight: 22,
    textAlign: "center",
  },
  problemPanel: {
    backgroundColor: CREAM,
    borderTopColor: "#d6d0ac",
    borderTopWidth: 1,
    marginHorizontal: 18,
    padding: 14,
  },
  problemTitle: {
    color: TEXT,
    fontSize: 16,
    fontWeight: "900",
    marginBottom: 8,
  },
  problemRow: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  problemItem: {
    alignItems: "center",
    flex: 1,
  },
  problemIcon: {
    color: NAVY,
    fontSize: 30,
    fontWeight: "900",
  },
  problemLabel: {
    color: TEXT,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 15,
    textAlign: "center",
  },
  metricsRow: {
    flexDirection: "row",
    gap: 10,
    marginHorizontal: 18,
    marginTop: 16,
  },
  metric: {
    backgroundColor: "#ffffff",
    borderColor: "#d2decf",
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    padding: 12,
  },
  metricLabel: {
    color: GREEN,
    fontSize: 11,
    fontWeight: "900",
    textTransform: "uppercase",
  },
  metricValue: {
    color: TEXT,
    fontSize: 24,
    fontWeight: "900",
    marginTop: 4,
  },
  actionButton: {
    alignItems: "center",
    backgroundColor: NAVY,
    borderRadius: 8,
    justifyContent: "center",
    marginHorizontal: 18,
    marginTop: 16,
    minHeight: 54,
  },
  actionButtonText: {
    color: "#ffffff",
    fontSize: 17,
    fontWeight: "900",
  },
  formPanel: {
    backgroundColor: "#ffffff",
    borderColor: "#d8dfd4",
    borderRadius: 8,
    borderWidth: 1,
    marginHorizontal: 18,
    marginBottom: 16,
    padding: 16,
  },
  inlineFields: {
    flexDirection: "row",
    gap: 12,
  },
  panelTitle: {
    color: TEXT,
    fontSize: 22,
    fontWeight: "900",
    marginBottom: 12,
  },
  chips: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 14,
  },
  chip: {
    backgroundColor: "#edf2e7",
    borderColor: "#c9d6c2",
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  chipActive: {
    backgroundColor: NAVY,
    borderColor: NAVY,
  },
  chipText: {
    color: TEXT,
    fontSize: 13,
    fontWeight: "800",
  },
  chipTextActive: {
    color: "#ffffff",
  },
  smallNote: {
    color: "#5d6b60",
    fontSize: 14,
    marginHorizontal: 18,
    marginTop: 12,
  },
  muted: {
    color: "#5d6b60",
    fontSize: 15,
  },
  inspectionMap: {
    backgroundColor: "#c5d2a6",
    height: 318,
    marginHorizontal: 18,
    overflow: "hidden",
    position: "relative",
  },
  satellitePatchA: {
    backgroundColor: "#728b50",
    height: 460,
    left: -20,
    opacity: 0.85,
    position: "absolute",
    top: 0,
    transform: [{ rotate: "-14deg" }],
    width: 230,
  },
  satellitePatchB: {
    backgroundColor: "#b85035",
    height: 510,
    left: 195,
    opacity: 0.78,
    position: "absolute",
    top: -40,
    transform: [{ rotate: "16deg" }],
    width: 210,
  },
  routeOne: {
    borderColor: "#ffffff",
    borderLeftWidth: 6,
    borderStyle: "dashed",
    height: 160,
    left: 182,
    position: "absolute",
    top: 128,
    transform: [{ rotate: "30deg" }],
  },
  routeTwo: {
    borderColor: "#ffffff",
    borderLeftWidth: 6,
    borderStyle: "dashed",
    height: 135,
    left: 230,
    position: "absolute",
    top: 70,
    transform: [{ rotate: "-6deg" }],
  },
  bluePin: {
    backgroundColor: "#307ed2",
    borderColor: "#ffffff",
    borderRadius: 22,
    borderWidth: 4,
    height: 44,
    left: 226,
    position: "absolute",
    top: 76,
    width: 44,
  },
  notePin: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    borderColor: "#1d2a3a",
    borderRadius: 20,
    borderWidth: 2,
    height: 40,
    justifyContent: "center",
    position: "absolute",
    right: 28,
    top: 206,
    width: 40,
  },
  notePinText: {
    color: NAVY,
    fontSize: 18,
    fontWeight: "900",
  },
  inspectionActions: {
    backgroundColor: CREAM,
    flexDirection: "row",
    gap: 18,
    justifyContent: "center",
    marginHorizontal: 18,
    paddingVertical: 14,
  },
  bigRound: {
    alignItems: "center",
    backgroundColor: NAVY,
    borderColor: "#b5d7f1",
    borderRadius: 60,
    borderWidth: 4,
    height: 120,
    justifyContent: "center",
    width: 120,
  },
  bigRoundIcon: {
    color: "#ffffff",
    fontSize: 18,
    fontWeight: "900",
    marginBottom: 4,
  },
  bigRoundText: {
    color: "#ffffff",
    fontSize: 14,
    fontWeight: "900",
    lineHeight: 18,
    textAlign: "center",
  },
  syncPanel: {
    backgroundColor: CREAM,
    marginHorizontal: 18,
    padding: 16,
  },
  syncText: {
    color: TEXT,
    fontSize: 17,
    fontWeight: "800",
    textAlign: "center",
  },
  progressTrack: {
    backgroundColor: "#ffffff",
    borderColor: NAVY,
    borderRadius: 999,
    borderWidth: 1,
    height: 16,
    marginTop: 12,
    overflow: "hidden",
  },
  progressFill: {
    backgroundColor: NAVY,
    height: "100%",
    width: "78%",
  },
  logoutButton: {
    alignItems: "center",
    backgroundColor: "#8f2d2d",
    borderRadius: 8,
    justifyContent: "center",
    marginTop: 18,
    minHeight: 52,
  },
  logoutButtonText: {
    color: "#ffffff",
    fontSize: 17,
    fontWeight: "900",
  },
  messageBox: {
    backgroundColor: "#fff7cf",
    borderColor: "#d6c16a",
    borderRadius: 8,
    borderWidth: 1,
    margin: 18,
    padding: 12,
  },
  messageText: {
    color: TEXT,
    fontSize: 14,
    fontWeight: "700",
  },
  bottomNav: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    borderTopColor: "#d6decf",
    borderTopWidth: 1,
    bottom: 0,
    flexDirection: "row",
    height: 80,
    justifyContent: "space-around",
    left: 0,
    paddingBottom: 8,
    position: "absolute",
    right: 0,
  },
  bottomItem: {
    alignItems: "center",
    flex: 1,
    gap: 5,
  },
  bottomDot: {
    backgroundColor: "#d3ded0",
    borderRadius: 14,
    height: 28,
    width: 28,
  },
  bottomDotActive: {
    backgroundColor: GREEN,
  },
  bottomText: {
    color: "#617064",
    fontSize: 12,
    fontWeight: "800",
  },
  bottomTextActive: {
    color: NAVY,
  },
});

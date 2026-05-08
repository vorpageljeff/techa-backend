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
      [-54.758904, -25.403677],
      [-54.761599, -25.405996],
      [-54.762379, -25.408426],
      [-54.763043, -25.412373],
      [-54.762256, -25.416528],
      [-54.761999, -25.424226],
      [-54.752944, -25.422894],
      [-54.749339, -25.415181],
      [-54.751714, -25.405543],
      [-54.758904, -25.403677],
    ],
  ],
};

const DEMO_FARMS = [
  {
    id: "demo-campo-9",
    name: "Campo 9 test",
    city: "Campo 9 paraguay",
    state: "Alto Parana",
    crop: "Soja",
    area_ha: 137.4,
  },
  { id: "demo-fredrich", name: "Fazenda Fredrich", city: "Acailandia", state: "Maranhao" },
  { id: "demo-bj", name: "Fazenda piloto BJ", city: "Marechal", state: "Alto Parana" },
  { id: "demo-esperanca", name: "Fazenda Esperanca", city: "Minga Guazu", state: "Alto Parana" },
  { id: "demo-progresso", name: "Fazenda Progresso", city: "Ciudad del Este", state: "Alto Parana" },
  { id: "demo-sao-joao", name: "Fazenda Sao Joao", city: "Hernandarias", state: "Alto Parana" },
];

const DEMO_FIELD = {
  id: "demo-talhao-norte",
  farm_id: "demo-campo-9",
  name: "Talhao Norte",
  crop: "Soja",
  area_ha: 137.4,
  planting_date: "2026-01-10",
  latest_ndvi: 0.545,
  ndvi_min: 0.164,
  ndvi_max: 0.655,
  latest_ndvi_date: "2026-04-23",
};

const DEMO_ANOMALIES = [
  {
    id: "demo-anomaly-1",
    field_id: "demo-talhao-norte",
    field_name: "Talhao Norte",
    farm_name: "Campo 9 test",
    detected_at: "2026-05-06T19:58:00Z",
    ndvi_drop_pct: 35.2,
    affected_area_ha: 104.5,
    suspected_type: "A Identificar",
    status: "active",
    location_lat: -25.46506,
    location_lon: -54.77357,
  },
  {
    id: "demo-anomaly-2",
    field_id: "demo-area-2",
    field_name: "Area 2 Teste Minga Guazu",
    farm_name: "Fazenda Esperanca",
    detected_at: "2026-05-06T20:10:00Z",
    ndvi_drop_pct: 23.9,
    affected_area_ha: 143.3,
    suspected_type: "A Identificar",
    status: "dismissed",
  },
];

const HISTORY = [
  ["23/4/2026", 0.545],
  ["18/4/2026", 0.554],
  ["8/4/2026", 0.539],
  ["26/3/2026", 0.418],
];

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

function formatHa(value) {
  if (value === null || value === undefined) return "-";
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(number >= 100 ? 1 : 0)} ha` : "-";
}

function formatNdvi(value) {
  const number = Number(value ?? 0.545);
  return number.toFixed(3);
}

function issueLabel(value) {
  const normalized = `${value || "A Identificar"}`.replace(/_/g, " ");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export default function App() {
  const [token, setToken] = useState("");
  const [user, setUser] = useState(null);
  const [screen, setScreen] = useState("farms");
  const [authMode, setAuthMode] = useState("register");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(null);
  const [farms, setFarms] = useState([]);
  const [fieldsByFarm, setFieldsByFarm] = useState({});
  const [dashboard, setDashboard] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [selectedFarm, setSelectedFarm] = useState(null);
  const [selectedField, setSelectedField] = useState(null);
  const [selectedAnomaly, setSelectedAnomaly] = useState(null);
  const [fieldTab, setFieldTab] = useState("map");
  const [reportReady, setReportReady] = useState(false);
  const [authForm, setAuthForm] = useState({
    name: "Jefferson Teste",
    email: `teste-${Date.now()}@techa.app`,
    password: "123456",
  });
  const [farmForm, setFarmForm] = useState({
    name: "Campo 9 test",
    crop: "Soja",
    city: "Campo 9 paraguay",
    state: "Alto Parana",
    area_ha: "137",
  });
  const [fieldForm, setFieldForm] = useState({
    farm_id: "",
    name: "Talhao Norte",
    crop: "Soja",
    planting_date: "2026-01-10",
  });

  const isLoggedIn = Boolean(token && user);
  const displayFarms = farms.length ? farms : DEMO_FARMS;
  const allFields = useMemo(() => Object.values(fieldsByFarm).flat(), [fieldsByFarm]);
  const displayFields = allFields.length ? allFields : [DEMO_FIELD];
  const displayAnomalies = anomalies.length
    ? anomalies.map((item) => ({
        ...item,
        field_name:
          item.field_name || displayFields.find((field) => field.id === item.field_id)?.name || "Talhao",
      }))
    : DEMO_ANOMALIES;

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
      const profile = await apiRequest("/api/v1/auth/me", { token: login.access_token });

      setToken(login.access_token);
      setUser(profile);
      setScreen("farms");
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
      setSelectedFarm(farm);
      setFieldForm((current) => ({ ...current, farm_id: farm.id }));
      await loadAppData();
      setScreen("fields");
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function createField() {
    const farmId = fieldForm.farm_id || selectedFarm?.id || farms[0]?.id;
    if (!farmId) {
      setMessage("Crie uma fazenda antes de criar talhoes.");
      return;
    }

    setBusy(true);
    setMessage("");
    try {
      const field = await apiRequest(`/api/v1/farms/${farmId}/fields`, {
        method: "POST",
        token,
        body: JSON.stringify({
          name: fieldForm.name.trim(),
          crop: fieldForm.crop.trim() || null,
          planting_date: fieldForm.planting_date || null,
          geometry: SAMPLE_POLYGON,
        }),
      });
      setSelectedField(field);
      await loadAppData();
      setScreen("fieldDetail");
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    setToken("");
    setUser(null);
    setFarms([]);
    setFieldsByFarm({});
    setAnomalies([]);
    setSelectedFarm(null);
    setSelectedField(null);
    setSelectedAnomaly(null);
    setScreen("farms");
  }

  function openFarm(farm) {
    setSelectedFarm(farm);
    setFieldForm((current) => ({ ...current, farm_id: farm.id }));
    setScreen("fields");
  }

  function openField(field) {
    setSelectedField(field);
    setFieldTab("map");
    setScreen("fieldDetail");
  }

  function openAnomaly(anomaly) {
    setSelectedAnomaly(anomaly);
    setScreen("anomalyDetail");
  }

  useEffect(() => {
    loadHealth();
  }, []);

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style={isLoggedIn ? "light" : "dark"} />
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.keyboard}
      >
        {!isLoggedIn ? (
          <AuthScreen
            health={health}
            authMode={authMode}
            setAuthMode={setAuthMode}
            form={authForm}
            setForm={setAuthForm}
            busy={busy}
            message={message}
            onSubmit={submitAuth}
            onRefresh={loadHealth}
          />
        ) : (
          <View style={styles.appShell}>
            {screen === "farms" && (
              <FarmsScreen
                farms={displayFarms}
                loading={loading}
                onRefresh={() => loadAppData()}
                onOpenFarm={openFarm}
                onAdd={() => setScreen("farmForm")}
              />
            )}
            {screen === "farmForm" && (
              <FarmFormScreen
                form={farmForm}
                setForm={setFarmForm}
                busy={busy}
                onBack={() => setScreen("farms")}
                onSave={createFarm}
              />
            )}
            {screen === "fields" && (
              <FieldsScreen
                farm={selectedFarm || displayFarms[0]}
                fields={
                  selectedFarm && fieldsByFarm[selectedFarm.id]?.length
                    ? fieldsByFarm[selectedFarm.id]
                    : displayFields
                }
                onBack={() => setScreen("farms")}
                onOpenField={openField}
                onAdd={() => setScreen("fieldForm")}
              />
            )}
            {screen === "fieldForm" && (
              <FieldFormScreen
                form={fieldForm}
                setForm={setFieldForm}
                busy={busy}
                onBack={() => setScreen("fields")}
                onSave={createField}
              />
            )}
            {screen === "fieldDetail" && (
              <FieldDetailScreen
                field={selectedField || displayFields[0]}
                anomalies={displayAnomalies}
                tab={fieldTab}
                setTab={setFieldTab}
                onBack={() => setScreen("fields")}
                onOpenAnomaly={openAnomaly}
                onReport={() => setScreen("report")}
              />
            )}
            {screen === "alerts" && (
              <AlertsScreen anomalies={displayAnomalies} onOpenAnomaly={openAnomaly} />
            )}
            {screen === "anomalyDetail" && (
              <AnomalyDetailScreen
                anomaly={selectedAnomaly || displayAnomalies[0]}
                onBack={() => setScreen("alerts")}
                onInspect={() => setScreen("inspectionForm")}
              />
            )}
            {screen === "inspectionForm" && (
              <InspectionFormScreen onBack={() => setScreen("anomalyDetail")} />
            )}
            {screen === "report" && (
              <ReportScreen
                field={selectedField || displayFields[0]}
                ready={reportReady}
                setReady={setReportReady}
                onBack={() => setScreen("fieldDetail")}
              />
            )}
            {screen === "profile" && <ProfileScreen user={user} onLogout={logout} />}
            {["farms", "alerts", "profile"].includes(screen) && (
              <BottomTabs value={screen} onChange={setScreen} />
            )}
            {!!message && <Toast text={message} />}
          </View>
        )}
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
  message,
  onSubmit,
  onRefresh,
}) {
  const isRegister = authMode === "register";

  return (
    <ScrollView contentContainerStyle={styles.authScreen} keyboardShouldPersistTaps="handled">
      <AppLogo />
      <Text style={styles.authTitle}>Techa</Text>
      <Text style={styles.authSubtitle}>Inteligencia que antecipa o que o olho humano nao ve.</Text>
      <View style={styles.healthCard}>
        <View>
          <Text style={styles.healthLabel}>API</Text>
          <Text style={styles.healthStatus}>{health?.status || "..."}</Text>
          <Text style={styles.healthHint}>Banco: {health?.database || "..."}</Text>
        </View>
        <Pressable style={styles.refreshCircle} onPress={onRefresh}>
          <Text style={styles.refreshCircleText}>R</Text>
        </Pressable>
      </View>
      <View style={styles.authSwitch}>
        {[
          ["register", "Cadastro"],
          ["login", "Login"],
        ].map(([key, label]) => (
          <Pressable
            key={key}
            style={[styles.authSwitchButton, authMode === key && styles.authSwitchActive]}
            onPress={() => setAuthMode(key)}
          >
            <Text style={[styles.authSwitchText, authMode === key && styles.authSwitchTextActive]}>
              {label}
            </Text>
          </Pressable>
        ))}
      </View>
      {isRegister && (
        <Input
          label="Nome"
          value={form.name}
          onChangeText={(value) => setForm((current) => ({ ...current, name: value }))}
        />
      )}
      <Input
        label="E-mail"
        value={form.email}
        autoCapitalize="none"
        keyboardType="email-address"
        onChangeText={(value) => setForm((current) => ({ ...current, email: value }))}
      />
      <Input
        label="Senha"
        value={form.password}
        secureTextEntry
        onChangeText={(value) => setForm((current) => ({ ...current, password: value }))}
      />
      <PrimaryButton
        label={isRegister ? "Criar conta" : "Entrar"}
        busy={busy}
        onPress={onSubmit}
      />
      {!!message && <Toast text={message} />}
    </ScrollView>
  );
}

function FarmsScreen({ farms, loading, onRefresh, onOpenFarm, onAdd }) {
  return (
    <Screen>
      <TopBar title="Fazendas" />
      <ScrollView contentContainerStyle={styles.contentWithFab}>
        <Text style={styles.listCount}>{farms.length} FAZENDAS REGISTRADAS</Text>
        {farms.map((farm) => (
          <FarmCard key={farm.id} farm={farm} onPress={() => onOpenFarm(farm)} />
        ))}
        <Pressable style={styles.subtleRefresh} onPress={onRefresh}>
          <Text style={styles.subtleRefreshText}>{loading ? "Atualizando..." : "Atualizar dados"}</Text>
        </Pressable>
      </ScrollView>
      <Fab onPress={onAdd} />
    </Screen>
  );
}

function FarmFormScreen({ form, setForm, busy, onBack, onSave }) {
  return (
    <Screen>
      <TopBar title="Nova Fazenda" backLabel="Fazendas" onBack={onBack} />
      <ScrollView contentContainerStyle={styles.formContent}>
        <Input
          label="Nome"
          value={form.name}
          onChangeText={(value) => setForm((current) => ({ ...current, name: value }))}
        />
        <Input
          label="Cidade"
          value={form.city}
          onChangeText={(value) => setForm((current) => ({ ...current, city: value }))}
        />
        <Input
          label="Estado"
          value={form.state}
          onChangeText={(value) => setForm((current) => ({ ...current, state: value }))}
        />
        <Input
          label="Area ha"
          value={form.area_ha}
          keyboardType="numeric"
          onChangeText={(value) => setForm((current) => ({ ...current, area_ha: value }))}
        />
        <PrimaryButton label="Salvar Fazenda" busy={busy} onPress={onSave} />
      </ScrollView>
    </Screen>
  );
}

function FieldsScreen({ farm, fields, onBack, onOpenField, onAdd }) {
  return (
    <Screen>
      <TopBar title="Talhoes" backLabel="(tabs)" onBack={onBack} />
      <View style={styles.farmBand}>
        <Text style={styles.farmBandTitle}>⌂ {farm?.name || "Campo 9 test"}</Text>
        <Text style={styles.farmBandSubtitle}>{farm?.city || "Campo 9 paraguay"}</Text>
      </View>
      <ScrollView contentContainerStyle={styles.contentWithFab}>
        <Text style={styles.listCount}>{fields.length} PARCELA REGISTRADA</Text>
        {fields.map((field) => (
          <FieldCard key={field.id} field={field} onPress={() => onOpenField(field)} />
        ))}
      </ScrollView>
      <Fab onPress={onAdd} />
    </Screen>
  );
}

function FieldFormScreen({ form, setForm, busy, onBack, onSave }) {
  return (
    <Screen>
      <TopBar title="Novo Talhao" backLabel="Talhoes" onBack={onBack} />
      <ScrollView contentContainerStyle={styles.formContent}>
        <Input
          label="Nome do talhao"
          value={form.name}
          onChangeText={(value) => setForm((current) => ({ ...current, name: value }))}
        />
        <Input
          label="Cultura"
          value={form.crop}
          onChangeText={(value) => setForm((current) => ({ ...current, crop: value }))}
        />
        <Input
          label="Semeadura"
          value={form.planting_date}
          onChangeText={(value) => setForm((current) => ({ ...current, planting_date: value }))}
        />
        <PrimaryButton label="Criar Talhao Demo" busy={busy} onPress={onSave} />
      </ScrollView>
    </Screen>
  );
}

function FieldDetailScreen({ field, anomalies, tab, setTab, onBack, onOpenAnomaly, onReport }) {
  const activeAnomaly = anomalies.find((item) => item.status === "active");
  const ndvi = field.latest_ndvi ?? 0.545;

  return (
    <Screen>
      <TopBar title="Talhao" backLabel="Talhoes" onBack={onBack} />
      <ScrollView contentContainerStyle={styles.fieldDetailContent}>
        <View style={styles.fieldHeader}>
          <View>
            <Text style={styles.fieldHeaderName}>{field.name || "Parcela"}</Text>
            <Text style={styles.fieldHeaderMeta}>Ultimo analisis: 23/4/2026</Text>
          </View>
          <View style={styles.ndviPill}>
            <View style={styles.ndviDot} />
            <Text style={styles.ndviPillText}>{formatNdvi(ndvi)} Normal</Text>
          </View>
          <View style={styles.downloadBadge}>
            <Text style={styles.downloadBadgeText}>Baixar mapa offline</Text>
          </View>
        </View>

        {!!activeAnomaly && (
          <Pressable style={styles.alertStrip} onPress={() => onOpenAnomaly(activeAnomaly)}>
            <Text style={styles.alertStripIcon}>!</Text>
            <View style={styles.alertStripTextWrap}>
              <Text style={styles.alertStripTitle}>1 anomalia activa</Text>
              <Text style={styles.alertStripText}>Toque para ver detalhes e navegar al lugar</Text>
            </View>
            <Text style={styles.chevronRed}>›</Text>
          </Pressable>
        )}

        <View style={styles.segmentTabs}>
          <Pressable
            style={[styles.segmentTab, tab === "map" && styles.segmentTabActive]}
            onPress={() => setTab("map")}
          >
            <Text style={[styles.segmentTabText, tab === "map" && styles.segmentTabTextActive]}>
              Mapa NDVI
            </Text>
          </Pressable>
          <Pressable
            style={[styles.segmentTab, tab === "history" && styles.segmentTabActive]}
            onPress={() => setTab("history")}
          >
            <Text style={[styles.segmentTabText, tab === "history" && styles.segmentTabTextActive]}>
              Historial
            </Text>
          </Pressable>
        </View>

        {tab === "map" ? <NdviMapCard field={field} /> : <HistoryList />}
      </ScrollView>
      <ReportFab onPress={onReport} />
    </Screen>
  );
}

function AlertsScreen({ anomalies, onOpenAnomaly }) {
  return (
    <Screen>
      <TopBar title="Alertas" />
      <ScrollView contentContainerStyle={styles.contentWithTabs}>
        {anomalies.map((anomaly, index) => (
          <AlertCard
            key={anomaly.id}
            anomaly={anomaly}
            tone={index === 0 ? "danger" : "warning"}
            onPress={() => onOpenAnomaly(anomaly)}
          />
        ))}
      </ScrollView>
    </Screen>
  );
}

function AnomalyDetailScreen({ anomaly, onBack, onInspect }) {
  return (
    <Screen>
      <TopBar title="Anomalia Detectada" onBack={onBack} />
      <ScrollView contentContainerStyle={styles.anomalyContent}>
        <View style={styles.satelliteHero}>
          <SatelliteBlocks />
          <View style={styles.redPin}>
            <Text style={styles.redPinText}>!</Text>
          </View>
          <View style={styles.heroBadge}>
            <Text style={styles.heroBadgeText}>{formatHa(anomaly.affected_area_ha)} afetados</Text>
          </View>
        </View>
        <View style={styles.statGrid}>
          <StatCard tone="danger" value={`${Math.round(anomaly.ndvi_drop_pct || 35)}%`} label="Queda de vigor" />
          <StatCard value={formatHa(anomaly.affected_area_ha)} label="Area afetada" />
        </View>
        <View style={styles.suspectBox}>
          <Text style={styles.suspectMark}>?</Text>
          <View>
            <Text style={styles.suspectTitle}>Suspeita: {issueLabel(anomaly.suspected_type)}</Text>
            <Text style={styles.suspectText}>Visitar o local e registrar observacoes</Text>
          </View>
        </View>
        <View style={styles.detailBox}>
          <Text style={styles.sectionTitle}>DETALHES DA DETECCAO</Text>
          <Text style={styles.detailLine}>Detectado em 06/05/2026 as 19:58</Text>
          <Text style={styles.detailLine}>-25.46506, -54.77357</Text>
          <Text style={styles.detailLine}>Fonte: Sentinel-2 (ESA/Copernicus)</Text>
        </View>
        <OutlineButton label="Registrar Inspecao" onPress={onInspect} />
        <PrimaryButton label="Confirmar no Campo" onPress={onInspect} />
        <DangerButton label="Descartar - Falso Positivo" />
      </ScrollView>
    </Screen>
  );
}

function InspectionFormScreen({ onBack }) {
  const [selected, setSelected] = useState("Deficiencia Nutricional");
  const [notes, setNotes] = useState("");
  const options = [
    "Praga / Inseto",
    "Doenca Foliar",
    "Estresse Hidrico",
    "Deficiencia Nutricional",
    "Dano Mecanico",
    "Outro",
  ];

  return (
    <Screen light>
      <TopBar title="Registrar Inspecao" onBack={onBack} rounded />
      <ScrollView contentContainerStyle={styles.inspectionContent}>
        <Text style={styles.sectionTitle}>FOTO DO PROBLEMA</Text>
        <Pressable style={styles.photoDrop}>
          <Text style={styles.photoIcon}>▢</Text>
          <Text style={styles.photoText}>Toque para fotografar</Text>
        </Pressable>
        <Text style={styles.sectionTitle}>O QUE ENCONTROU?</Text>
        <View style={styles.issueGrid}>
          {options.map((option) => (
            <Pressable
              key={option}
              style={[styles.issueChip, selected === option && styles.issueChipActive]}
              onPress={() => setSelected(option)}
            >
              <Text style={[styles.issueChipText, selected === option && styles.issueChipTextActive]}>
                {option}
              </Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.sectionTitle}>OBSERVACOES (OPCIONAL)</Text>
        <TextInput
          multiline
          value={notes}
          onChangeText={setNotes}
          placeholder="Descreva o que observou no campo..."
          placeholderTextColor={MUTED}
          style={styles.notesInput}
        />
        <PrimaryButton label="Salvar Inspecao" onPress={onBack} />
      </ScrollView>
    </Screen>
  );
}

function ReportScreen({ field, ready, setReady, onBack }) {
  return (
    <Screen light>
      <TopBar title="Relatorio do Talhao" backLabel="Talhao" onBack={onBack} />
      <ScrollView contentContainerStyle={styles.reportContent}>
        <View style={styles.reportHero}>
          <Text style={styles.reportIcon}>▥</Text>
          <View>
            <Text style={styles.reportHeroTitle}>Informe NDVI</Text>
            <Text style={styles.reportHeroSubtitle}>{field.name || "Talhao Norte"}</Text>
          </View>
        </View>
        <View style={styles.reportBox}>
          <Text style={styles.reportIntro}>El informe incluye:</Text>
          {[
            "Mapa de vigor NDVI con escala de colores",
            "Historial de analisis Sentinel-2",
            "Anomalias detectadas y areas afectadas",
            "Inspecciones de campo registradas",
            "Recomendaciones agronomicas",
          ].map((line) => (
            <Text key={line} style={styles.reportLine}>
              {line}
            </Text>
          ))}
        </View>
        <View style={styles.divider} />
        <Text style={styles.reportSection}>PDF</Text>
        <PrimaryButton label="Generar y Descargar PDF" onPress={() => setReady(true)} />
        {ready && (
          <View style={styles.readyModal}>
            <Text style={styles.readyTitle}>Informe listo!</Text>
            <Text style={styles.readyText}>PDF gerado. Toque Abrir / Compartir para ver.</Text>
            <Pressable style={styles.readyButton} onPress={() => setReady(false)}>
              <Text style={styles.readyButtonText}>OK</Text>
            </Pressable>
          </View>
        )}
        <OutlineButton label="Abrir / Compartir PDF" />
        <View style={styles.divider} />
        <Text style={styles.reportSection}>Enviar por WhatsApp</Text>
        <Input label="Numero del destinatario" placeholder="Ej: 595999999999" />
        <PrimaryButton label="Enviar Informe por WhatsApp" />
      </ScrollView>
    </Screen>
  );
}

function ProfileScreen({ user, onLogout }) {
  return (
    <Screen dark>
      <TopBar title="Perfil" transparent />
      <ScrollView contentContainerStyle={styles.profileContent}>
        <View style={styles.profileCard}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{(user.name || "C").charAt(0).toUpperCase()}</Text>
          </View>
          <Text style={styles.profileName}>{user.name || "Caio Lambert"}</Text>
          <Text style={styles.profileEmail}>{user.email}</Text>
          <View style={styles.planPill}>
            <Text style={styles.planPillText}>Plan {user.plan || "Pro"}</Text>
          </View>
        </View>
        <View style={styles.settingsCard}>
          <Text style={styles.settingsTitle}>APARIENCIA</Text>
          <SettingRow icon="☼" label="Claro" />
          <SettingRow icon="☾" label="Oscuro" active />
          <SettingRow icon="▯" label="Sistema" />
        </View>
        <Pressable style={styles.logoutOutline} onPress={onLogout}>
          <Text style={styles.logoutOutlineText}>Cerrar Sesion</Text>
        </Pressable>
        <Text style={styles.versionText}>Techa v1.0.0 · InnovAgro Py</Text>
      </ScrollView>
    </Screen>
  );
}

function FarmCard({ farm, onPress }) {
  return (
    <Pressable style={styles.listCard} onPress={onPress}>
      <View style={styles.leafTile}>
        <Text style={styles.leafIcon}>⌒</Text>
      </View>
      <View style={styles.listMain}>
        <Text style={styles.listTitle}>{farm.name}</Text>
        <Text style={styles.listSubtitle}>
          {farm.city || "Sem cidade"}, {farm.state || "PY"} · talhoes
        </Text>
      </View>
      <Text style={styles.chevron}>›</Text>
    </Pressable>
  );
}

function FieldCard({ field, onPress }) {
  return (
    <Pressable style={styles.listCard} onPress={onPress}>
      <View style={styles.leafTile}>
        <Text style={styles.leafIcon}>⌒</Text>
      </View>
      <View style={styles.listMain}>
        <Text style={styles.listTitle}>{field.name}</Text>
        <Text style={styles.listSubtitle}>
          {field.crop || "Soja"} · {formatHa(field.area_ha || 137.4)}
        </Text>
        <Text style={styles.listMuted}>Siembra: {field.planting_date || "2026-01-10"}</Text>
      </View>
      <View style={styles.statusDot} />
      <Text style={styles.chevron}>›</Text>
    </Pressable>
  );
}

function AlertCard({ anomaly, tone, onPress }) {
  const active = anomaly.status === "active";
  return (
    <Pressable style={styles.alertCard} onPress={onPress}>
      <View style={[styles.alertSide, tone === "warning" && styles.alertSideWarning]} />
      <View style={styles.alertCardBody}>
        <View style={styles.alertTop}>
          <Text style={styles.alertTitle}>{anomaly.field_name || "Talhao Norte"}</Text>
          <Text style={styles.alertTime}>hace 1 dia</Text>
        </View>
        <View style={styles.alertMetrics}>
          <View>
            <Text style={[styles.alertMetricValue, tone === "warning" && styles.warningText]}>
              ↘ {Math.round(anomaly.ndvi_drop_pct || 35)}%
            </Text>
            <Text style={styles.alertMetricLabel}>Caida NDVI</Text>
          </View>
          <View>
            <Text style={styles.alertMetricValue}>{formatHa(anomaly.affected_area_ha)}</Text>
            <Text style={styles.alertMetricLabel}>Area Afectada</Text>
          </View>
          <View>
            <Text style={styles.alertMetricValue}>{issueLabel(anomaly.suspected_type)}</Text>
            <Text style={styles.alertMetricLabel}>Sospecha</Text>
          </View>
        </View>
        <View style={styles.alertBottom}>
          <View style={[styles.statusBadge, !active && styles.statusBadgeResolved]}>
            <Text style={styles.statusBadgeText}>{active ? "Activo" : "Resuelto"}</Text>
          </View>
          <Text style={styles.navigateText}>Navegar →</Text>
        </View>
      </View>
    </Pressable>
  );
}

function NdviMapCard({ field }) {
  return (
    <>
      <View style={styles.ndviMap}>
        <SatelliteBlocks />
        <View style={styles.ndviFieldOverlay}>
          <View style={styles.ndviZoneGreen} />
          <View style={styles.ndviZoneLight} />
          <View style={styles.ndviZoneYellow} />
          <View style={styles.ndviZoneRed} />
        </View>
      </View>
      <View style={styles.legendRow}>
        <Legend color="#dc2626" label="Critico < 0,2" />
        <Legend color="#f59e0b" label="Alerta 0,2-0,4" />
        <Legend color="#84cc16" label="Normal 0,4-0,6" />
        <Legend color="#16a34a" label="Otimo > 0,6" />
      </View>
      <View style={styles.ndviStats}>
        <MiniStat value={formatNdvi(field.ndvi_min ?? 0.164)} label="Minimo" />
        <MiniStat value={formatNdvi(field.latest_ndvi ?? 0.545)} label="Promedio" />
        <MiniStat value={formatNdvi(field.ndvi_max ?? 0.655)} label="Maximo" />
      </View>
    </>
  );
}

function HistoryList() {
  return (
    <View style={styles.historyList}>
      {HISTORY.map(([date, ndvi]) => (
        <View key={date} style={styles.historyRow}>
          <Text style={styles.historyDate}>{date}</Text>
          <View style={styles.historyRight}>
            <View style={styles.ndviPillSmall}>
              <View style={styles.ndviDot} />
              <Text style={styles.ndviPillSmallText}>{formatNdvi(ndvi)} Normal</Text>
            </View>
            <Text style={styles.checkText}>✓</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

function SatelliteBlocks() {
  return (
    <View style={styles.satelliteBlocks}>
      <View style={styles.satBlockA} />
      <View style={styles.satBlockB} />
      <View style={styles.satBlockC} />
      <View style={styles.satRoadOne} />
      <View style={styles.satRoadTwo} />
      <View style={styles.satForest} />
    </View>
  );
}

function StatCard({ value, label, tone }) {
  return (
    <View style={[styles.statCard, tone === "danger" && styles.statCardDanger]}>
      <Text style={[styles.statValue, tone === "danger" && styles.dangerText]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function SettingRow({ icon, label, active }) {
  return (
    <View style={styles.settingRow}>
      <Text style={[styles.settingIcon, active && styles.settingActive]}>{icon}</Text>
      <Text style={[styles.settingLabel, active && styles.settingActive]}>{label}</Text>
      {active && <Text style={styles.settingCheck}>✓</Text>}
    </View>
  );
}

function Legend({ color, label }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendDot, { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
  );
}

function MiniStat({ value, label }) {
  return (
    <View style={styles.miniStat}>
      <Text style={styles.miniStatValue}>{value}</Text>
      <Text style={styles.miniStatLabel}>{label}</Text>
    </View>
  );
}

function Screen({ children, dark, light }) {
  return <View style={[styles.screenBody, dark && styles.darkBody, light && styles.lightBody]}>{children}</View>;
}

function TopBar({ title, backLabel, onBack, transparent, rounded }) {
  return (
    <View style={[styles.topBar, transparent && styles.topBarTransparent, rounded && styles.topBarRounded]}>
      {onBack ? (
        <Pressable style={styles.backPill} onPress={onBack}>
          <Text style={styles.backText}>‹ {backLabel || ""}</Text>
        </Pressable>
      ) : (
        <View style={styles.backSpace} />
      )}
      <Text style={styles.topTitle}>{title}</Text>
      <View style={styles.backSpace} />
    </View>
  );
}

function BottomTabs({ value, onChange }) {
  const tabs = [
    ["farms", "⌂", "Fazendas"],
    ["alerts", "△", "Alertas"],
    ["profile", "♙", "Perfil"],
  ];

  return (
    <View style={styles.bottomTabs}>
      {tabs.map(([key, icon, label]) => (
        <Pressable key={key} style={styles.tabButton} onPress={() => onChange(key)}>
          <Text style={[styles.tabIcon, value === key && styles.tabActive]}>{icon}</Text>
          <Text style={[styles.tabText, value === key && styles.tabActive]}>{label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function Fab({ onPress }) {
  return (
    <Pressable style={styles.fab} onPress={onPress}>
      <Text style={styles.fabText}>+</Text>
    </Pressable>
  );
}

function ReportFab({ onPress }) {
  return (
    <Pressable style={styles.reportFab} onPress={onPress}>
      <Text style={styles.reportFabText}>▤</Text>
    </Pressable>
  );
}

function Input({ label, ...props }) {
  return (
    <View style={styles.inputGroup}>
      {!!label && <Text style={styles.inputLabel}>{label}</Text>}
      <TextInput placeholderTextColor={MUTED} style={styles.input} {...props} />
    </View>
  );
}

function PrimaryButton({ label, busy, onPress }) {
  return (
    <Pressable style={styles.primaryButton} onPress={onPress} disabled={busy}>
      {busy ? <ActivityIndicator color="#ffffff" /> : <Text style={styles.primaryButtonText}>{label}</Text>}
    </Pressable>
  );
}

function OutlineButton({ label, onPress }) {
  return (
    <Pressable style={styles.outlineButton} onPress={onPress}>
      <Text style={styles.outlineButtonText}>{label}</Text>
    </Pressable>
  );
}

function DangerButton({ label, onPress }) {
  return (
    <Pressable style={styles.dangerButton} onPress={onPress}>
      <Text style={styles.dangerButtonText}>{label}</Text>
    </Pressable>
  );
}

function Toast({ text }) {
  return (
    <View style={styles.toast}>
      <Text style={styles.toastText}>{text}</Text>
    </View>
  );
}

function AppLogo() {
  return (
    <View style={styles.appLogo}>
      <Text style={styles.appLogoT}>T</Text>
      <View style={styles.logoLineRed} />
      <View style={styles.logoLineYellow} />
      <View style={styles.logoLineGreen} />
      <Text style={styles.logoWord}>TECHA</Text>
    </View>
  );
}

const DARK = "#07170d";
const DARK_2 = "#0d2418";
const GREEN = "#18a957";
const GREEN_DARK = "#145334";
const TEXT = "#111827";
const MUTED = "#8c939c";
const BG = "#f6f7f9";
const RED = "#dc2626";
const YELLOW = "#f59e0b";

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: DARK },
  keyboard: { flex: 1 },
  appShell: { flex: 1, backgroundColor: BG },
  screenBody: { flex: 1, backgroundColor: BG },
  darkBody: { backgroundColor: DARK },
  lightBody: { backgroundColor: BG },
  authScreen: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    flexGrow: 1,
    padding: 28,
    paddingTop: 82,
  },
  appLogo: {
    alignItems: "center",
    backgroundColor: GREEN_DARK,
    borderRadius: 36,
    height: 150,
    justifyContent: "center",
    marginBottom: 20,
    shadowColor: GREEN_DARK,
    shadowOpacity: 0.25,
    shadowRadius: 18,
    width: 150,
  },
  appLogoT: { color: "#ffffff", fontSize: 80, fontWeight: "900", lineHeight: 86 },
  logoLineRed: { backgroundColor: "#9b3a2f", borderRadius: 3, height: 6, width: 86 },
  logoLineYellow: { backgroundColor: "#b69222", borderRadius: 3, height: 6, marginTop: 4, width: 78 },
  logoLineGreen: { backgroundColor: "#2f8f45", borderRadius: 3, height: 6, marginTop: 4, width: 70 },
  logoWord: { color: "#d9e5dd", fontSize: 12, letterSpacing: 4, marginTop: 14 },
  authTitle: { color: TEXT, fontSize: 34, fontWeight: "900" },
  authSubtitle: { color: "#626b75", fontSize: 15, marginBottom: 18, textAlign: "center" },
  healthCard: {
    alignItems: "center",
    backgroundColor: "#ecf7ef",
    borderColor: "#cfe6d7",
    borderRadius: 22,
    borderWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 18,
    padding: 18,
    width: "100%",
  },
  healthLabel: { color: GREEN_DARK, fontSize: 13, fontWeight: "900" },
  healthStatus: { color: TEXT, fontSize: 26, fontWeight: "900" },
  healthHint: { color: "#5d6962", fontSize: 14 },
  refreshCircle: {
    alignItems: "center",
    backgroundColor: GREEN_DARK,
    borderRadius: 28,
    height: 56,
    justifyContent: "center",
    width: 56,
  },
  refreshCircleText: { color: "#ffffff", fontSize: 22, fontWeight: "900" },
  authSwitch: {
    backgroundColor: "#edf1ee",
    borderRadius: 16,
    flexDirection: "row",
    marginBottom: 18,
    padding: 5,
    width: "100%",
  },
  authSwitchButton: { alignItems: "center", borderRadius: 12, flex: 1, paddingVertical: 12 },
  authSwitchActive: { backgroundColor: GREEN_DARK },
  authSwitchText: { color: "#66706a", fontSize: 16, fontWeight: "800" },
  authSwitchTextActive: { color: "#ffffff" },
  topBar: {
    alignItems: "center",
    backgroundColor: DARK,
    flexDirection: "row",
    height: 92,
    justifyContent: "space-between",
    paddingHorizontal: 30,
    paddingTop: 14,
  },
  topBarTransparent: { backgroundColor: DARK },
  topBarRounded: { borderBottomLeftRadius: 34, borderBottomRightRadius: 34, height: 112 },
  topTitle: { color: "#ffffff", flex: 1, fontSize: 24, fontWeight: "900", textAlign: "center" },
  backPill: {
    alignItems: "center",
    borderColor: "rgba(255,255,255,0.12)",
    borderRadius: 26,
    borderWidth: 1,
    minWidth: 96,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  backText: { color: "#ffffff", fontSize: 22, fontWeight: "800" },
  backSpace: { minWidth: 96 },
  contentWithTabs: { padding: 30, paddingBottom: 120 },
  contentWithFab: { padding: 30, paddingBottom: 170 },
  listCount: { color: "#7c828c", fontSize: 16, letterSpacing: 2.4, marginBottom: 18 },
  listCard: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    borderRadius: 22,
    flexDirection: "row",
    marginBottom: 18,
    padding: 26,
    shadowColor: "#152216",
    shadowOpacity: 0.07,
    shadowRadius: 18,
  },
  leafTile: {
    alignItems: "center",
    backgroundColor: "#ecfff4",
    borderRadius: 16,
    height: 58,
    justifyContent: "center",
    marginRight: 20,
    width: 58,
  },
  leafIcon: { color: GREEN, fontSize: 34, fontWeight: "900", transform: [{ rotate: "-25deg" }] },
  listMain: { flex: 1 },
  listTitle: { color: TEXT, fontSize: 24, fontWeight: "900" },
  listSubtitle: { color: "#68707a", fontSize: 18, lineHeight: 24, marginTop: 2 },
  listMuted: { color: "#9aa1aa", fontSize: 17, marginTop: 2 },
  chevron: { color: "#9aa1aa", fontSize: 42, fontWeight: "300" },
  chevronRed: { color: RED, fontSize: 36, fontWeight: "300" },
  statusDot: { backgroundColor: GREEN, borderRadius: 7, height: 14, marginRight: 14, width: 14 },
  subtleRefresh: { alignItems: "center", padding: 16 },
  subtleRefreshText: { color: GREEN_DARK, fontSize: 15, fontWeight: "800" },
  fab: {
    alignItems: "center",
    backgroundColor: GREEN,
    borderRadius: 42,
    bottom: 84,
    height: 84,
    justifyContent: "center",
    position: "absolute",
    right: 38,
    shadowColor: GREEN,
    shadowOpacity: 0.35,
    shadowRadius: 22,
    width: 84,
  },
  fabText: { color: "#ffffff", fontSize: 42, fontWeight: "300", marginTop: -3 },
  farmBand: { backgroundColor: GREEN_DARK, padding: 30 },
  farmBandTitle: { color: "#ffffff", fontSize: 26, fontWeight: "900" },
  farmBandSubtitle: { color: "#cadbd1", fontSize: 18, marginTop: 4 },
  fieldDetailContent: { paddingBottom: 160 },
  fieldHeader: {
    alignItems: "flex-start",
    backgroundColor: "#ffffff",
    borderBottomColor: "#e5e7eb",
    borderBottomWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    padding: 30,
  },
  fieldHeaderName: { color: TEXT, fontSize: 25, fontWeight: "900" },
  fieldHeaderMeta: { color: "#6b7280", fontSize: 17, marginTop: 2 },
  ndviPill: {
    alignItems: "center",
    borderColor: "#84cc16",
    borderRadius: 22,
    borderWidth: 1.5,
    flexDirection: "row",
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  ndviDot: { backgroundColor: "#84cc16", borderRadius: 7, height: 14, marginRight: 8, width: 14 },
  ndviPillText: { color: "#84cc16", fontSize: 16, fontWeight: "900" },
  downloadBadge: {
    backgroundColor: "#9aa4b2",
    borderRadius: 9,
    bottom: 30,
    paddingHorizontal: 12,
    paddingVertical: 6,
    position: "absolute",
    right: 30,
  },
  downloadBadgeText: { color: "#ffffff", fontSize: 14, fontWeight: "800" },
  alertStrip: {
    alignItems: "center",
    backgroundColor: "#fff1f2",
    borderBottomColor: "#fecdd3",
    borderBottomWidth: 1,
    flexDirection: "row",
    padding: 30,
  },
  alertStripIcon: { color: RED, fontSize: 34, fontWeight: "900", marginRight: 18 },
  alertStripTextWrap: { flex: 1 },
  alertStripTitle: { color: "#991b1b", fontSize: 22, fontWeight: "900" },
  alertStripText: { color: "#dc2626", fontSize: 17, marginTop: 2 },
  segmentTabs: {
    backgroundColor: "#ffffff",
    borderBottomColor: "#e5e7eb",
    borderBottomWidth: 1,
    flexDirection: "row",
  },
  segmentTab: { alignItems: "center", flex: 1, paddingVertical: 22 },
  segmentTabActive: { borderBottomColor: GREEN, borderBottomWidth: 3 },
  segmentTabText: { color: "#6b7280", fontSize: 21, fontWeight: "700" },
  segmentTabTextActive: { color: GREEN, fontWeight: "900" },
  ndviMap: { height: 520, overflow: "hidden", position: "relative" },
  satelliteBlocks: { flex: 1, backgroundColor: "#587b4c", position: "relative" },
  satBlockA: { backgroundColor: "#78935e", height: 650, left: -60, position: "absolute", top: -40, transform: [{ rotate: "-15deg" }], width: 260 },
  satBlockB: { backgroundColor: "#ba6f4d", height: 650, left: 250, position: "absolute", top: -80, transform: [{ rotate: "15deg" }], width: 250 },
  satBlockC: { backgroundColor: "#b55c38", height: 560, left: 180, opacity: 0.75, position: "absolute", top: 170, transform: [{ rotate: "14deg" }], width: 170 },
  satRoadOne: { backgroundColor: "rgba(220,210,170,0.35)", height: 34, left: -40, position: "absolute", top: 40, transform: [{ rotate: "-13deg" }], width: 580 },
  satRoadTwo: { backgroundColor: "rgba(220,210,170,0.35)", height: 30, left: 60, position: "absolute", top: 260, transform: [{ rotate: "28deg" }], width: 520 },
  satForest: { backgroundColor: "#173d22", height: 140, position: "absolute", right: 0, top: 80, width: 90 },
  ndviFieldOverlay: {
    backgroundColor: "#20a650",
    borderColor: "#ddd145",
    borderWidth: 3,
    height: 300,
    left: "37%",
    overflow: "hidden",
    position: "absolute",
    top: 120,
    width: "34%",
  },
  ndviZoneGreen: { backgroundColor: "#179946", bottom: 0, height: 150, left: 0, position: "absolute", right: 0 },
  ndviZoneLight: { backgroundColor: "#7ecb3d", height: 180, left: 0, position: "absolute", top: 0, width: "70%" },
  ndviZoneYellow: { backgroundColor: "#cfd338", height: 190, position: "absolute", right: 0, top: 0, width: "34%" },
  ndviZoneRed: { backgroundColor: "#d6342e", height: 150, position: "absolute", right: 0, top: 20, width: "23%" },
  legendRow: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    paddingHorizontal: 20,
    paddingVertical: 18,
  },
  legendItem: { alignItems: "center", flexDirection: "row" },
  legendDot: { borderRadius: 7, height: 14, marginRight: 5, width: 14 },
  legendText: { color: "#6b7280", fontSize: 13 },
  ndviStats: { flexDirection: "row", gap: 16, padding: 26 },
  miniStat: { alignItems: "center", backgroundColor: "#ffffff", borderRadius: 18, flex: 1, paddingVertical: 22 },
  miniStatValue: { color: TEXT, fontSize: 27, fontWeight: "900" },
  miniStatLabel: { color: "#6b7280", fontSize: 16, marginTop: 4 },
  historyList: { padding: 26 },
  historyRow: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    borderRadius: 16,
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 14,
    padding: 22,
  },
  historyDate: { color: "#374151", fontSize: 22, fontWeight: "800" },
  historyRight: { alignItems: "center", flexDirection: "row" },
  ndviPillSmall: {
    alignItems: "center",
    borderColor: "#84cc16",
    borderRadius: 20,
    borderWidth: 1.5,
    flexDirection: "row",
    marginRight: 12,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  ndviPillSmallText: { color: "#84cc16", fontSize: 14, fontWeight: "900" },
  checkText: { color: GREEN, fontSize: 20 },
  alertCard: {
    backgroundColor: "#ffffff",
    borderRadius: 20,
    flexDirection: "row",
    marginBottom: 20,
    overflow: "hidden",
  },
  alertSide: { backgroundColor: RED, width: 8 },
  alertSideWarning: { backgroundColor: YELLOW },
  alertCardBody: { flex: 1, padding: 24 },
  alertTop: { flexDirection: "row", justifyContent: "space-between" },
  alertTitle: { color: TEXT, fontSize: 22, fontWeight: "900" },
  alertTime: { color: "#9ca3af", fontSize: 16 },
  alertMetrics: { flexDirection: "row", justifyContent: "space-between", marginTop: 18 },
  alertMetricValue: { color: TEXT, fontSize: 20, fontWeight: "900" },
  alertMetricLabel: { color: "#6b7280", fontSize: 15, marginTop: 2 },
  warningText: { color: YELLOW },
  alertBottom: { alignItems: "center", flexDirection: "row", justifyContent: "space-between", marginTop: 18 },
  statusBadge: { backgroundColor: "#fee2e2", borderRadius: 18, paddingHorizontal: 14, paddingVertical: 8 },
  statusBadgeResolved: { backgroundColor: "#f3f4f6" },
  statusBadgeText: { color: "#4b5563", fontSize: 16, fontWeight: "800" },
  navigateText: { color: GREEN, fontSize: 18, fontWeight: "900" },
  anomalyContent: { backgroundColor: BG, paddingBottom: 40 },
  satelliteHero: { height: 360, overflow: "hidden", position: "relative" },
  redPin: {
    alignItems: "center",
    backgroundColor: RED,
    borderColor: "#ffffff",
    borderRadius: 27,
    borderWidth: 4,
    height: 54,
    justifyContent: "center",
    left: "47%",
    position: "absolute",
    top: 125,
    width: 54,
  },
  redPinText: { color: "#ffffff", fontSize: 24, fontWeight: "900" },
  heroBadge: { backgroundColor: "rgba(220,38,38,0.88)", borderRadius: 8, bottom: 16, left: 16, paddingHorizontal: 12, paddingVertical: 7, position: "absolute" },
  heroBadgeText: { color: "#ffffff", fontSize: 17, fontWeight: "900" },
  statGrid: { flexDirection: "row", gap: 18, padding: 30 },
  statCard: { backgroundColor: "#ffffff", borderRadius: 18, flex: 1, padding: 24 },
  statCardDanger: { borderTopColor: RED, borderTopWidth: 4 },
  statValue: { color: TEXT, fontSize: 32, fontWeight: "900" },
  dangerText: { color: RED },
  statLabel: { color: "#6b7280", fontSize: 16, marginTop: 6 },
  suspectBox: { alignItems: "center", backgroundColor: "#fffbeb", borderColor: "#fde68a", borderRadius: 16, borderWidth: 1, flexDirection: "row", marginHorizontal: 30, padding: 20 },
  suspectMark: { color: RED, fontSize: 42, fontWeight: "900", marginRight: 24 },
  suspectTitle: { color: "#92400e", fontSize: 20, fontWeight: "900" },
  suspectText: { color: "#92400e", fontSize: 17, marginTop: 4 },
  detailBox: { backgroundColor: "#ffffff", borderRadius: 18, margin: 30, padding: 24 },
  sectionTitle: { color: "#374151", fontSize: 18, fontWeight: "900", letterSpacing: 1.5, marginBottom: 14 },
  detailLine: { color: "#4b5563", fontSize: 18, lineHeight: 30 },
  inspectionContent: { padding: 30, paddingBottom: 60 },
  photoDrop: { alignItems: "center", backgroundColor: "#ffffff", borderColor: "#e5e7eb", borderRadius: 18, borderStyle: "dashed", borderWidth: 2, height: 205, justifyContent: "center", marginBottom: 30 },
  photoIcon: { color: "#9ca3af", fontSize: 48 },
  photoText: { color: "#6b7280", fontSize: 19, marginTop: 10 },
  issueGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginBottom: 28 },
  issueChip: { backgroundColor: "#ffffff", borderColor: "#d1d5db", borderRadius: 25, borderWidth: 1.5, paddingHorizontal: 18, paddingVertical: 11 },
  issueChipActive: { backgroundColor: "#e8f8ef", borderColor: GREEN },
  issueChipText: { color: "#374151", fontSize: 16, fontWeight: "700" },
  issueChipTextActive: { color: GREEN, fontWeight: "900" },
  notesInput: { backgroundColor: "#ffffff", borderColor: "#e5e7eb", borderRadius: 18, borderWidth: 1.5, color: TEXT, fontSize: 18, minHeight: 130, padding: 20, textAlignVertical: "top" },
  reportContent: { padding: 30, paddingBottom: 80 },
  reportHero: { alignItems: "center", backgroundColor: GREEN_DARK, borderRadius: 22, flexDirection: "row", marginBottom: 26, padding: 28 },
  reportIcon: { color: "#ffffff", fontSize: 52, marginRight: 22 },
  reportHeroTitle: { color: "#ffffff", fontSize: 28, fontWeight: "900" },
  reportHeroSubtitle: { color: "#b6cbbf", fontSize: 18, marginTop: 4 },
  reportBox: { backgroundColor: "#ffffff", borderRadius: 20, padding: 26 },
  reportIntro: { color: TEXT, fontSize: 20, fontWeight: "900", marginBottom: 18 },
  reportLine: { color: "#374151", fontSize: 18, lineHeight: 35 },
  divider: { backgroundColor: "#e5e7eb", height: 1, marginVertical: 28 },
  reportSection: { color: TEXT, fontSize: 22, fontWeight: "900", marginBottom: 12 },
  readyModal: { backgroundColor: "rgba(17,24,39,0.88)", borderRadius: 26, left: 40, padding: 28, position: "absolute", right: 40, top: 330, zIndex: 10 },
  readyTitle: { color: "#ffffff", fontSize: 24, fontWeight: "900" },
  readyText: { color: "#d1d5db", fontSize: 18, lineHeight: 26, marginTop: 10 },
  readyButton: { alignItems: "center", backgroundColor: "rgba(255,255,255,0.2)", borderRadius: 22, marginTop: 22, paddingVertical: 14 },
  readyButtonText: { color: "#ffffff", fontSize: 18, fontWeight: "900" },
  profileContent: { padding: 38, paddingBottom: 120 },
  profileCard: { alignItems: "center", backgroundColor: DARK_2, borderColor: "rgba(255,255,255,0.12)", borderRadius: 24, borderWidth: 1, padding: 42 },
  avatar: { alignItems: "center", backgroundColor: "#116b35", borderRadius: 54, height: 108, justifyContent: "center", marginBottom: 22, width: 108 },
  avatarText: { color: "#ffffff", fontSize: 42, fontWeight: "900" },
  profileName: { color: "#ffffff", fontSize: 27, fontWeight: "900" },
  profileEmail: { color: "#aab4bd", fontSize: 19, marginTop: 8 },
  planPill: { backgroundColor: "#0f7d3f", borderRadius: 22, marginTop: 18, paddingHorizontal: 22, paddingVertical: 8 },
  planPillText: { color: "#3ee07a", fontSize: 16, fontWeight: "900" },
  settingsCard: { backgroundColor: DARK_2, borderColor: "rgba(255,255,255,0.12)", borderRadius: 24, borderWidth: 1, marginTop: 28, padding: 28 },
  settingsTitle: { color: "#aab4bd", fontSize: 16, fontWeight: "900", letterSpacing: 2, marginBottom: 16 },
  settingRow: { alignItems: "center", borderBottomColor: "rgba(255,255,255,0.08)", borderBottomWidth: 1, flexDirection: "row", paddingVertical: 18 },
  settingIcon: { color: "#9ca3af", fontSize: 28, marginRight: 22, width: 28 },
  settingLabel: { color: "#ffffff", flex: 1, fontSize: 21, fontWeight: "700" },
  settingActive: { color: GREEN },
  settingCheck: { color: GREEN, fontSize: 22 },
  logoutOutline: { alignItems: "center", borderColor: "#fb7185", borderRadius: 20, borderWidth: 2, marginTop: 28, paddingVertical: 22 },
  logoutOutlineText: { color: "#fb7185", fontSize: 22, fontWeight: "900" },
  versionText: { color: "#6b7280", fontSize: 16, marginTop: 28, textAlign: "center" },
  bottomTabs: {
    alignItems: "center",
    backgroundColor: DARK_2,
    borderTopColor: "rgba(255,255,255,0.08)",
    borderTopWidth: 1,
    bottom: 0,
    flexDirection: "row",
    height: 90,
    justifyContent: "space-around",
    left: 0,
    paddingBottom: 12,
    position: "absolute",
    right: 0,
  },
  tabButton: { alignItems: "center", flex: 1 },
  tabIcon: { color: "#6b7280", fontSize: 27, fontWeight: "900" },
  tabText: { color: "#6b7280", fontSize: 14, fontWeight: "800", marginTop: 2 },
  tabActive: { color: "#22d36e" },
  reportFab: { alignItems: "center", backgroundColor: GREEN_DARK, borderRadius: 38, bottom: 40, height: 76, justifyContent: "center", position: "absolute", right: 38, width: 76 },
  reportFabText: { color: "#ffffff", fontSize: 32 },
  inputGroup: { marginBottom: 18, width: "100%" },
  inputLabel: { color: TEXT, fontSize: 16, fontWeight: "900", marginBottom: 8 },
  input: { backgroundColor: "#ffffff", borderColor: "#e5e7eb", borderRadius: 16, borderWidth: 1.5, color: TEXT, fontSize: 18, minHeight: 56, paddingHorizontal: 18 },
  formContent: { padding: 30 },
  primaryButton: { alignItems: "center", backgroundColor: GREEN, borderRadius: 18, justifyContent: "center", marginTop: 18, minHeight: 64 },
  primaryButtonText: { color: "#ffffff", fontSize: 20, fontWeight: "900" },
  outlineButton: { alignItems: "center", backgroundColor: "#ffffff", borderColor: GREEN, borderRadius: 18, borderWidth: 2, justifyContent: "center", marginHorizontal: 30, marginTop: 14, minHeight: 64 },
  outlineButtonText: { color: GREEN, fontSize: 20, fontWeight: "900" },
  dangerButton: { alignItems: "center", backgroundColor: "#ffffff", borderColor: RED, borderRadius: 18, borderWidth: 2, justifyContent: "center", marginHorizontal: 30, marginTop: 18, minHeight: 64 },
  dangerButtonText: { color: RED, fontSize: 20, fontWeight: "900" },
  toast: { backgroundColor: "#fffbeb", borderColor: "#fde68a", borderRadius: 16, borderWidth: 1, bottom: 104, left: 24, padding: 14, position: "absolute", right: 24 },
  toastText: { color: "#92400e", fontSize: 14, fontWeight: "800" },
});

// Explicaciones en lenguaje sencillo para el modo básico: qué ha pasado y
// qué conviene hacer, a partir del título y el origen de cada alerta. Las
// firmas de Suricata (ET SCAN..., ET POLICY...) se traducen por su tipo; lo
// que no se reconoce se queda con una explicación genérica según la gravedad.

import type { Alert, AlertSeverity } from "@/lib/types";

export interface PlainAlert {
  title: string;      // qué ha pasado, en una frase
  what: string;       // un poco más de contexto
  todo: string;       // qué hacer
}

const RULES: { test: RegExp; plain: Omit<PlainAlert, "title"> & { title: string } }[] = [
  {
    test: /nuevo dispositivo en cuarentena/i,
    plain: {
      title: "Un equipo nuevo está esperando tu permiso",
      what: "Se ha conectado un equipo que no conocemos. Como la cuarentena está activa, todavía no puede salir a Internet.",
      todo: "Si es tuyo (un móvil, una tele…), márcalo como de confianza. Si no lo reconoces, bloquéalo.",
    },
  },
  {
    test: /nuevo dispositivo/i,
    plain: {
      title: "Se ha conectado un equipo nuevo",
      what: "Un aparato que no habíamos visto antes se ha unido a tu red.",
      todo: "Comprueba que lo reconoces. Si es tuyo, márcalo como de confianza; si no, bloquéalo.",
    },
  },
  {
    test: /cambio de ip/i,
    plain: {
      title: "Un equipo ha cambiado de dirección",
      what: "Es normal cuando un aparato se reconecta.",
      todo: "No hace falta hacer nada.",
    },
  },
  {
    test: /listas? de amenazas|blocklist|feodo|firehol/i,
    plain: {
      title: "Un equipo intentó hablar con un sitio peligroso",
      what: "Intentó conectarse a una dirección de Internet conocida por estar relacionada con virus o ataques. LanSentinel cortó la conexión.",
      todo: "Pasa un antivirus a ese equipo y, si no sabes qué es, bloquéalo hasta revisarlo.",
    },
  },
  {
    test: /bloqueo automático/i,
    plain: {
      title: "LanSentinel ha bloqueado una amenaza",
      what: "Detectó algo grave y bloqueó automáticamente al responsable.",
      todo: "Si crees que es un error (por ejemplo, era un equipo tuyo), puedes desbloquearlo desde su ficha.",
    },
  },
  {
    test: /servicios inseguros|telnet|ftp/i,
    plain: {
      title: "Un equipo tiene una puerta poco segura abierta",
      what: "Ofrece un servicio antiguo que se puede espiar o atacar con facilidad (por ejemplo, sin contraseña o sin cifrar).",
      todo: "Actualiza ese aparato o desactiva ese servicio en su configuración. Si es una cámara o un enchufe inteligente, busca actualizaciones del fabricante.",
    },
  },
  {
    test: /nuevos puertos abiertos/i,
    plain: {
      title: "Un equipo ha abierto nuevas puertas",
      what: "Ahora acepta conexiones por sitios por los que antes no lo hacía.",
      todo: "Si acabas de instalar algo en él, es normal. Si no, revísalo.",
    },
  },
  {
    test: /inusual|pico de consumo/i,
    plain: {
      title: "Un equipo está usando mucha más Internet de lo normal",
      what: "Ha enviado o descargado bastantes más datos de lo que suele.",
      todo: "Si estaba haciendo una copia en la nube o una actualización, es normal. Si no, podría estar infectado: revísalo.",
    },
  },
  {
    test: /puerta de enlace|gateway/i,
    plain: {
      title: "Ha cambiado el router de tu red",
      what: "El aparato que da salida a Internet ya no es el mismo. Pasa si cambias de router; si no, alguien podría estar haciéndose pasar por él.",
      todo: "Si no has cambiado el router, avisa a quien te ayude con la informática.",
    },
  },
  {
    test: /conflicto de ip|reclama la ip|arp/i,
    plain: {
      title: "Un equipo podría estar suplantando a otro",
      what: "Dos aparatos dicen tener la misma dirección. A veces es un fallo de configuración; otras, alguien intentando espiar el tráfico.",
      todo: "Si se repite, revisa los equipos implicados o pide ayuda.",
    },
  },
  {
    test: /copia de seguridad|copias/i,
    plain: {
      title: "Problema con las copias de seguridad",
      what: "LanSentinel no ha podido guardar su copia de seguridad.",
      todo: "Revisa el espacio en disco del equipo de LanSentinel o pide ayuda.",
    },
  },
  {
    test: /scan|escaneo|nmap|recon/i,
    plain: {
      title: "Alguien está explorando tu red",
      what: "Un equipo está probando puertas en tus aparatos, como quien prueba qué ventanas están abiertas. A veces es un programa legítimo; otras, el paso previo a un ataque.",
      todo: "Si viene de fuera, LanSentinel suele bloquearlo solo. Si viene de un equipo de casa que no reconoces, bloquéalo.",
    },
  },
  {
    test: /brute|fuerza bruta|login|password|contraseña/i,
    plain: {
      title: "Alguien intenta adivinar una contraseña",
      what: "Se han visto muchos intentos seguidos de entrar con contraseñas distintas.",
      todo: "Usa contraseñas largas en tus aparatos. Si viene de un equipo de casa, revísalo.",
    },
  },
  {
    test: /malware|trojan|troyano|botnet|\bc2\b|cnc|exploit|ransom/i,
    plain: {
      title: "Posible virus o ataque en tu red",
      what: "El tráfico de un equipo se parece al de un programa malicioso conocido.",
      todo: "Desconecta o bloquea ese equipo y pásale un antivirus.",
    },
  },
  {
    test: /user-agent|user_agents|policy|ET INFO|ET HUNTING/i,
    plain: {
      title: "Tráfico extraño en un equipo",
      what: "Un programa se ha comportado de forma poco habitual. Muchas veces es inofensivo.",
      todo: "Si se repite mucho o el equipo no es tuyo, revísalo.",
    },
  },
];

const GENERIC: Record<AlertSeverity, Omit<PlainAlert, "title">> = {
  critical: { what: "LanSentinel ha visto algo grave en tu red.", todo: "Revisa el equipo afectado cuanto antes; si no sabes cómo, bloquéalo y pide ayuda." },
  high: { what: "Algo poco habitual que conviene revisar.", todo: "Comprueba el equipo afectado." },
  medium: { what: "Algo que merece un vistazo, pero no es urgente.", todo: "Échale un ojo cuando puedas." },
  low: { what: "Un aviso menor.", todo: "Normalmente no hace falta hacer nada." },
  info: { what: "Información, no un problema.", todo: "No hace falta hacer nada." },
};

export function explainAlert(alert: Pick<Alert, "title" | "severity" | "source" | "raw_payload">): PlainAlert {
  const category = (alert.raw_payload as { alert?: { category?: string } } | null)?.alert?.category ?? "";
  const text = `${alert.title} ${category}`;
  const rule = RULES.find(r => r.test.test(text));
  if (rule) return rule.plain;
  return { title: "Aviso de seguridad", ...GENERIC[alert.severity] };
}

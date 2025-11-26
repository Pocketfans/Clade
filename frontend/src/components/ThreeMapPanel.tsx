import { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { SSAOPass } from "three/examples/jsm/postprocessing/SSAOPass.js";
import { fetchHeightMap, fetchWaterMask, fetchErosionMap } from "../services/api";
import type { MapOverview, MapTileInfo } from "../services/api.types";
import { ViewMode } from "./MapViewSelector";

const PHYSICS_RES_X = 2048;
const PHYSICS_RES_Y = 640;
const MIN_ZOOM = 0.35;
const MAX_ZOOM = 4;
const FRICTION = 0.92;
const STOP_VELOCITY = 0.05;
const LOGIC_RES_X = 128;
const LOGIC_RES_Y = 40;

const MAP_ASPECT_RATIO = PHYSICS_RES_X / PHYSICS_RES_Y;
const BASE_VIEW_HEIGHT = 500;
const DETAIL_AMPLITUDE_METERS = 120;

const computeViewDimensions = (viewportWidth: number, viewportHeight: number) => {
  const viewportAspect = viewportWidth / Math.max(viewportHeight, 1);
  if (viewportAspect > MAP_ASPECT_RATIO) {
    const viewHeight = BASE_VIEW_HEIGHT;
    return { viewWidth: viewHeight * MAP_ASPECT_RATIO, viewHeight };
  }
  const viewWidth = BASE_VIEW_HEIGHT * viewportAspect;
  return { viewWidth, viewHeight: viewWidth / MAP_ASPECT_RATIO };
};

const VIEW_MODE_LABELS: Record<ViewMode, string> = {
  terrain: "基础地形",
  terrain_type: "地形分类",
  elevation: "海拔色阶",
  biodiversity: "生物多样性",
  climate: "气候分布",
  suitability: "物种适宜度",
};

// ==================== 简化调试Shader ====================
const debugVertexShader = `
uniform sampler2D heightMap;
uniform float scale;
varying vec2 vUv;
varying float vHeight;

void main() {
    vUv = uv;
    vec4 heightData = texture2D(heightMap, uv);
    vHeight = heightData.r;
    
    vec3 pos = position;
    pos.z += vHeight * scale;
    
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}
`;

const debugFragmentShader = `
varying vec2 vUv;
varying float vHeight;

void main() {
    // 调试：先直接显示UV坐标
    // gl_FragColor = vec4(vUv.x, vUv.y, 0.0, 1.0);  // UV可视化
    // return;
    
    // 调试：显示高度值是否被正确采样
    // if (abs(vHeight) < 0.01) {
    //     // 高度接近0的区域显示为红色
    //     gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0);
    //     return;
    // }
    
    // 简单的高度着色：蓝色=低，绿色=中，红色=高
    vec3 color;
    if (vHeight < 0.0) {
        // 水下 - 蓝色
        color = vec3(0.0, 0.3, 0.8);
    } else if (vHeight < 1000.0) {
        // 低地 - 绿色
        color = vec3(0.3, 0.7, 0.2);
    } else if (vHeight < 2000.0) {
        // 中地 - 黄色
        color = vec3(0.8, 0.7, 0.2);
    } else {
        // 高地 - 白色
        color = vec3(0.9, 0.9, 0.9);
    }
    
    gl_FragColor = vec4(color, 1.0);
}
`;

// ==================== 地形 Vertex Shader ====================
const terrainVertexShader = `
uniform sampler2D heightMap;
uniform sampler2D erosionMap;
uniform float scale;
uniform float detailAmplitude;
varying vec2 vUv;
varying float vHeight;
varying vec3 vPosition;
varying vec3 vWorldPosition;
varying vec3 vNormal;
varying float vDetail;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;
    float freq = 1.0;
    for (int i = 0; i < 5; i++) {
        value += amplitude * noise(p * freq);
        freq *= 2.0;
        amplitude *= 0.5;
    }
    return value;
}

void main() {
    vUv = uv;
    vec4 heightData = texture2D(heightMap, uv);
    vHeight = heightData.r;
    
    vec3 pos = position;
    pos.z += vHeight * scale;
    
    vec2 erosion = texture2D(erosionMap, uv).rg;
    float ridgeNoise = fbm(uv * 96.0);
    float detailMask = mix(0.35, 1.0, clamp(erosion.x * 1.5, 0.0, 1.0));
    float detailOffset = (ridgeNoise - 0.5) * detailAmplitude * detailMask;
    pos.z += detailOffset;
    vDetail = detailMask;
    
    vec4 worldPos = modelMatrix * vec4(pos, 1.0);
    vWorldPosition = worldPos.xyz;
    vPosition = pos;
    
    float px = 1.0 / 2048.0;
    float py = 1.0 / 640.0;
    
    float hL = texture2D(heightMap, uv + vec2(-px, 0.0)).r;
    float hR = texture2D(heightMap, uv + vec2(px, 0.0)).r;
    float hD = texture2D(heightMap, uv + vec2(0.0, -py)).r;
    float hU = texture2D(heightMap, uv + vec2(0.0, py)).r;
    
    float ridgeNoiseX = fbm((uv + vec2(px, 0.0)) * 96.0);
    float ridgeNoiseY = fbm((uv + vec2(0.0, py)) * 96.0);
    float detailDX = (ridgeNoiseX - ridgeNoise) * detailAmplitude * detailMask;
    float detailDY = (ridgeNoiseY - ridgeNoise) * detailAmplitude * detailMask;
    
    vec3 tangent = normalize(vec3(2.0, 0.0, (hR - hL) * scale * 3.0 + detailDX));
    vec3 bitangent = normalize(vec3(0.0, 2.0, (hU - hD) * scale * 3.0 + detailDY));
    vNormal = normalize(cross(tangent, bitangent));
    
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}
`;

// ==================== 地形 Fragment Shader（增强版）====================
const terrainFragmentShader = `
uniform sampler2D heightMap;
uniform sampler2D erosionMap;
uniform float scale;
uniform vec2 resolution;
uniform float time;

varying vec2 vUv;
varying float vHeight;
varying vec3 vPosition;
varying vec3 vWorldPosition;
varying vec3 vNormal;
varying float vDetail;

// Victoria 3 风格调色板（自然、去饱和）
vec3 c_beach = vec3(0.82, 0.76, 0.62);
vec3 c_grass_low = vec3(0.35, 0.52, 0.25);
vec3 c_grass_mid = vec3(0.45, 0.60, 0.28);
vec3 c_grass_high = vec3(0.40, 0.55, 0.22);
vec3 c_rock = vec3(0.42, 0.38, 0.35);
vec3 c_rock_dark = vec3(0.28, 0.26, 0.24);
vec3 c_snow = vec3(0.92, 0.94, 0.96);
vec3 c_dirt = vec3(0.55, 0.48, 0.38);

// ==================== 噪声函数 ====================
float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

// FBM（分形布朗运动）- 用于生成复杂纹理
float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;
    float frequency = 1.0;
    
    for (int i = 0; i < 5; i++) {
        value += amplitude * noise(p * frequency);
        frequency *= 2.0;
        amplitude *= 0.5;
    }
    return value;
}

// ==================== Triplanar Mapping ====================
vec3 triplanarTexture(vec3 pos, vec3 normal, float scale) {
    // 根据法线权重混合三个投影平面
    vec3 blending = abs(normal);
    blending = normalize(max(blending, 0.00001));
    float b = (blending.x + blending.y + blending.z);
    blending /= vec3(b);
    
    // 为每个轴采样纹理（使用FBM模拟纹理）
    float texX = fbm(pos.yz * scale);
    float texY = fbm(pos.xz * scale);
    float texZ = fbm(pos.xy * scale);
    
    float result = texX * blending.x + texY * blending.y + texZ * blending.z;
    return vec3(result);
}

// ==================== PBR光照模型 ====================
vec3 computePBRLighting(vec3 baseColor, vec3 normal, vec3 viewDir, float roughness, float metallic) {
    // 主光源（太阳光）
    vec3 lightDir = normalize(vec3(-0.8, -1.0, 0.9));
    vec3 lightColor = vec3(1.0, 0.98, 0.95);
    
    // 漫反射（Lambert）
    float NdotL = max(dot(normal, lightDir), 0.0);
    vec3 diffuse = baseColor * lightColor * NdotL;
    
    // 镜面反射（Blinn-Phong简化版）
    vec3 halfVec = normalize(lightDir + viewDir);
    float NdotH = max(dot(normal, halfVec), 0.0);
    float specPower = mix(32.0, 8.0, roughness);
    float spec = pow(NdotH, specPower) * (1.0 - roughness);
    vec3 specular = lightColor * spec * mix(vec3(0.04), baseColor, metallic);
    
    // 环境光（模拟天空光照）
    vec3 skyColor = vec3(0.4, 0.5, 0.7);
    vec3 groundColor = vec3(0.2, 0.15, 0.1);
    float skyFactor = normal.z * 0.5 + 0.5;
    vec3 ambient = mix(groundColor, skyColor, skyFactor) * baseColor * 0.3;
    
    // 边缘光（Rim Light）- 模拟大气散射
    float rimPower = 1.0 - max(dot(normal, viewDir), 0.0);
    vec3 rimColor = vec3(0.5, 0.65, 0.85) * pow(rimPower, 3.0) * 0.4;
    
    // 环境光遮蔽（基于坡度）
    float slope = 1.0 - normal.z;
    float ao = 1.0 - smoothstep(0.0, 0.6, slope) * 0.35;
    
    return (diffuse + specular + ambient) * ao + rimColor;
}

void main() {
    vec3 normal = normalize(vNormal);
    vec3 viewDir = normalize(cameraPosition - vWorldPosition);
    
    float slope = 1.0 - normal.z;
    vec2 erosionFactors = texture2D(erosionMap, vUv).rg;
    float hydro = erosionFactors.r;
    float aeolian = erosionFactors.g;
    
    // ==================== 材质混合 ====================
    
    // 1. 基础纹理采样（Triplanar Mapping）
    vec3 microDetail = triplanarTexture(vWorldPosition * 0.8 + normal * 0.25, normal, 0.15 + hydro * 0.05);
    vec3 macroDetail = triplanarTexture(vWorldPosition * 0.15 + normal * 0.05, normal, 0.05);
    vec2 warpedNoise = vec2(fbm(vUv * 6.0 + time * 0.01), fbm((vUv + vec2(0.23, -0.12)) * 8.0));
    
    // 2. 根据高度和坡度选择基础颜色
    vec3 baseColor;
    float roughness = 0.8;
    float metallic = 0.0;
    
    if (vHeight < 10.0) {
        // 海滩
        baseColor = mix(c_beach, c_dirt, microDetail.r * 0.3);
        roughness = 0.7;
    } else if (vHeight < 800.0) {
        // 低地草原
        baseColor = mix(c_grass_low, c_grass_mid, smoothstep(10.0, 800.0, vHeight));
        baseColor = mix(baseColor, c_grass_high, microDetail.r * 0.2);
        roughness = 0.85;
    } else if (vHeight < 1800.0) {
        // 中地草原到高地
        baseColor = mix(c_grass_mid, c_grass_high, smoothstep(800.0, 1800.0, vHeight));
        // 添加泥土斑块
        float dirtMask = fbm(vUv * 50.0);
        baseColor = mix(baseColor, c_dirt, dirtMask * 0.15);
        roughness = 0.82;
    } else if (vHeight < 2800.0) {
        // 岩石山地
        baseColor = mix(c_rock, c_rock_dark, macroDetail.r);
        roughness = 0.75;
    } else {
        // 雪山
        float snowBlend = smoothstep(2800.0, 3500.0, vHeight);
        baseColor = mix(c_rock, c_snow, snowBlend);
        // 雪的微观细节
        baseColor = mix(baseColor, vec3(0.88, 0.90, 0.93), microDetail.r * 0.15 * snowBlend);
        roughness = mix(0.75, 0.3, snowBlend);
    }
    
    baseColor = mix(baseColor, mix(c_dirt, vec3(0.22, 0.31, 0.38), 0.4), hydro * 0.25);
    baseColor = mix(baseColor, vec3(0.76, 0.68, 0.55), aeolian * 0.25);
    baseColor += (warpedNoise.x - 0.5) * 0.05;
    
    // 3. 坡度混合（陡峭处显示岩石）
    if (vHeight > 100.0 && vHeight < 3000.0) {
        float slopeMask = smoothstep(0.2, 0.5, slope);
        vec3 cliffRock = mix(c_rock_dark, c_rock, macroDetail.r);
        baseColor = mix(baseColor, cliffRock, slopeMask);
        roughness = mix(roughness, 0.75, slopeMask);
    }
    
    // 4. 应用细节纹理变化
    baseColor *= (0.92 + 0.16 * microDetail.r);
    roughness = mix(roughness, 0.95, hydro * 0.4);
    roughness = mix(roughness, 0.55, aeolian * 0.3);
    
    // ==================== PBR光照计算 ====================
    vec3 finalColor = computePBRLighting(baseColor, normal, viewDir, roughness, metallic);
    
    float hydroAO = mix(1.0, 0.85, smoothstep(0.25, 0.9, hydro));
    float dustGlow = mix(0.0, 0.08, aeolian);
    finalColor = finalColor * hydroAO + dustGlow;
    finalColor = mix(finalColor, vec3(0.6, 0.67, 0.7), aeolian * 0.08);
    
    // ==================== 深度雾效（可选）====================
    float distanceFromCamera = length(vWorldPosition - cameraPosition);
    float fogStart = 800.0;
    float fogEnd = 2500.0;
    float fogFactor = smoothstep(fogStart, fogEnd, distanceFromCamera);
    vec3 fogColor = vec3(0.75, 0.82, 0.92);
    finalColor = mix(finalColor, fogColor, fogFactor * 0.4);
    
    gl_FragColor = vec4(finalColor, 1.0);
}
`;

// ==================== 水体 Vertex Shader ====================
const waterVertexShader = `
uniform sampler2D heightMap;
uniform float scale;
uniform float time;
varying vec2 vUv;
varying vec3 vPosition;
varying vec3 vWorldPosition;
varying vec3 vNormal;
varying float vWaterDepth;

void main() {
    vUv = uv;
    vec4 heightData = texture2D(heightMap, uv);
    float terrainHeight = heightData.r;
    
    // 水面略高于海平面
    float waterHeight = max(0.0, -terrainHeight * 0.1);
    vWaterDepth = waterHeight;
    
    vec3 pos = position;
    // 添加波浪动画
    float wave = sin(pos.x * 0.02 + time) * cos(pos.y * 0.03 + time * 0.7) * 0.8;
    pos.z += wave;
    
    vec4 worldPos = modelMatrix * vec4(pos, 1.0);
    vWorldPosition = worldPos.xyz;
    vPosition = pos;
    
    // 水面法线（简化）
    vNormal = normalize(vec3(
        -cos(pos.x * 0.02 + time) * 0.016,
        -sin(pos.y * 0.03 + time * 0.7) * 0.024,
        1.0
    ));
    
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}
`;

// ==================== 水体 Fragment Shader ====================
const waterFragmentShader = `
uniform sampler2D heightMap;
uniform sampler2D waterMask;
uniform sampler2D erosionMap;
uniform float time;
varying vec2 vUv;
varying vec3 vPosition;
varying vec3 vWorldPosition;
varying vec3 vNormal;
varying float vWaterDepth;

// 水体颜色
vec3 c_shallow_water = vec3(0.1, 0.35, 0.45);
vec3 c_deep_water = vec3(0.02, 0.1, 0.18);
vec3 c_foam = vec3(0.92, 0.95, 0.98);

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
               mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

void main() {
    vec4 heightData = texture2D(heightMap, vUv);
    float terrainHeight = heightData.r;
    float maskDepth = texture2D(waterMask, vUv).r;
    vec2 erosionFactors = texture2D(erosionMap, vUv).rg;
    
    // 无水区域直接丢弃
    if (maskDepth <= 0.001) {
        discard;
    }
    
    float depth = maskDepth;  // 使用物理引擎水深
    
    vec3 normal = normalize(vNormal);
    vec3 viewDir = normalize(cameraPosition - vWorldPosition);
    
    // ==================== 水体颜色混合 ====================
    float depthFactor = smoothstep(0.0, 200.0, depth);
    vec3 waterColor = mix(c_shallow_water, c_deep_water, depthFactor);
    waterColor = mix(waterColor, vec3(0.06, 0.32, 0.42), erosionFactors.r * 0.4);
    waterColor += (noise(vUv * 50.0 + time * 0.03) - 0.5) * 0.05;
    
    // ==================== Fresnel反射 ====================
    float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 3.0);
    vec3 skyReflection = vec3(0.5, 0.65, 0.85);
    waterColor = mix(waterColor, skyReflection, fresnel * 0.6);
    
    // ==================== 镜面高光 ====================
    vec3 lightDir = normalize(vec3(-0.8, -1.0, 0.9));
    vec3 reflectDir = reflect(-lightDir, normal);
    float spec = pow(max(dot(viewDir, reflectDir), 0.0), 128.0);
    vec3 specular = vec3(1.0) * spec * 0.8;
    
    // ==================== 岸线泡沫 ====================
    float shoreDistance = smoothstep(-5.0, -30.0, terrainHeight);
    float foamNoise = noise(vUv * 100.0 + vec2(time * 0.05, time * 0.03));
    float foam = (1.0 - shoreDistance) * smoothstep(0.4, 0.7, foamNoise);
    float erosionFoam = mix(0.2, 1.0, erosionFactors.r);
    waterColor = mix(waterColor, c_foam, foam * erosionFoam * 0.7);
    
    // ==================== 最终颜色 ====================
    vec3 finalColor = waterColor + specular;
    
    // 透明度（深水更不透明）
    float alpha = mix(0.85, 0.95, depthFactor);
    alpha = mix(alpha, 0.98, erosionFactors.r * 0.3);
    
    gl_FragColor = vec4(finalColor, alpha);
}
`;

interface Props {
  map?: MapOverview | null;
  onRefresh: () => void;
  selectedTile?: MapTileInfo | null;
  onSelectTile: (tile: MapTileInfo, point: { clientX: number; clientY: number }) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  highlightSpeciesId?: string | null;
}

export const ThreeMapPanel = ({
  map,
  onRefresh,
  selectedTile,
  onSelectTile,
  viewMode,
  onViewModeChange,
  highlightSpeciesId,
}: Props) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.OrthographicCamera | null>(null);
  const terrainMaterialRef = useRef<THREE.ShaderMaterial | null>(null);
  const waterMaterialRef = useRef<THREE.ShaderMaterial | null>(null);
  const heightTextureRef = useRef<THREE.DataTexture | null>(null);
  const waterTextureRef = useRef<THREE.DataTexture | null>(null);
  const erosionTextureRef = useRef<THREE.DataTexture | null>(null);
  const composerRef = useRef<EffectComposer | null>(null);
  const terrainMeshRef = useRef<THREE.Mesh | null>(null);
  const waterMeshRef = useRef<THREE.Mesh | null>(null);
  const terrainGeometryRef = useRef<THREE.PlaneGeometry | null>(null);
  const waterGeometryRef = useRef<THREE.PlaneGeometry | null>(null);
  const controlsRef = useRef<{ zoomBy: (delta: number) => void; reset: () => void }>({
    zoomBy: () => {},
    reset: () => {},
  });
  const tileIndexRef = useRef<Map<string, MapTileInfo>>(new Map());
  const raycasterRef = useRef(new THREE.Raycaster());
  const pointerRef = useRef(new THREE.Vector2());
  const planeDimsRef = useRef({ width: 1, height: 1 });
  const hoverTileRef = useRef<MapTileInfo | null>(null);
  const lastPointerRef = useRef<{ clientX: number; clientY: number } | null>(null);
  const hoverHighlightRef = useRef<THREE.Mesh | null>(null);
  const selectionHighlightRef = useRef<THREE.Mesh | null>(null);
  const ssaoPassRef = useRef<SSAOPass | null>(null);
  const bloomPassRef = useRef<UnrealBloomPass | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [enablePostProcessing, setEnablePostProcessing] = useState(true);
  const [dataVersion, setDataVersion] = useState(0); // 用于追踪数据版本
  const enablePostProcessingRef = useRef(enablePostProcessing);

  useEffect(() => {
    enablePostProcessingRef.current = enablePostProcessing;
  }, [enablePostProcessing]);

  const handleManualRefresh = useCallback(() => {
    onRefresh();
    setDataVersion((prev) => prev + 1);
  }, [onRefresh]);

  const handleViewModeShortcut = useCallback(() => {
    const nextMode: ViewMode = viewMode === "suitability" ? "terrain" : "suitability";
    onViewModeChange(nextMode);
  }, [viewMode, onViewModeChange]);

  const viewModeLabel = VIEW_MODE_LABELS[viewMode] ?? viewMode;
  const viewModeShortcutLabel =
    viewMode === "suitability" ? "切换到基础地形" : "查看适宜度";
  const highlightedSpeciesLabel = highlightSpeciesId ?? "未选择物种";

  const getTileByLogicCoord = (lx: number, ly: number): MapTileInfo | null =>
    tileIndexRef.current.get(`${lx},${ly}`) ?? null;

  const hideHighlight = (mesh: THREE.Mesh | null) => {
    if (mesh) mesh.visible = false;
  };

  const positionHighlight = (mesh: THREE.Mesh | null, tile: MapTileInfo, zOffset = 8) => {
    if (!mesh) return;
    const { width, height } = planeDimsRef.current;
    if (width <= 1e-3 || height <= 1e-3) return;
    const worldX = (tile.x / LOGIC_RES_X - 0.5) * width;
    const worldY = (0.5 - tile.y / LOGIC_RES_Y) * height;
    mesh.position.set(worldX, worldY, zOffset);
    mesh.visible = true;
  };

  // 监听map变化，触发数据重新加载
  useEffect(() => {
    if (map) {
      console.log('[3D Map] Map data changed, triggering reload...');
      setDataVersion(prev => prev + 1);
    }
  }, [map?.turn_index]); // 监听回合变化

  useEffect(() => {
    const index = new Map<string, MapTileInfo>();
    map?.tiles.forEach((tile) => {
      index.set(`${tile.x},${tile.y}`, tile);
    });
    tileIndexRef.current = index;
  }, [map?.tiles]);

  useEffect(() => {
    if (!containerRef.current) return;

    // 1. Setup Three.js
    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e); // 恢复深色背景
    const { viewWidth, viewHeight } = computeViewDimensions(width, height);

    // Camera: Orthographic to show full map
    const camera = new THREE.OrthographicCamera(
      -viewWidth, viewWidth,
      viewHeight, -viewHeight,
      0.1, 10000
    );
    camera.position.set(0, 0, 1000);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ 
      antialias: true,
      alpha: false,
      powerPreference: "high-performance"
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); // 限制最大像素比
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    containerRef.current.appendChild(renderer.domElement);
    renderer.domElement.style.cursor = "grab";

    // 2. Create Plane with higher segments for better detail
    const segmentsX = 1024; // 提升到1024，更好地展现2048分辨率的细节
    const segmentsY = 320;  // 提升到320
    
    // 平面尺寸应该匹配地图纵横比
    const planeWidth = viewWidth * 1.8;
    const planeHeight = planeWidth / MAP_ASPECT_RATIO;
    
    const geometry = new THREE.PlaneGeometry(planeWidth, planeHeight, segmentsX, segmentsY);
    terrainGeometryRef.current = geometry;
    planeDimsRef.current = { width: planeWidth, height: planeHeight };
    
    console.log(`Map aspect: ${MAP_ASPECT_RATIO.toFixed(2)}, Plane size: ${planeWidth.toFixed(1)} x ${planeHeight.toFixed(1)}, Segments: ${segmentsX} x ${segmentsY}`);
    
    sceneRef.current = scene;
    cameraRef.current = camera;
    rendererRef.current = renderer;
    
    // 3. 设置后处理管线
    const composer = new EffectComposer(renderer);
    const renderPass = new RenderPass(scene, camera);
    composer.addPass(renderPass);
    
    // SSAO Pass - 屏幕空间环境光遮蔽（优化参数避免过暗）
    const ssaoPass = new SSAOPass(scene, camera, width, height);
    ssaoPass.kernelRadius = 8;  // 减小半径
    ssaoPass.minDistance = 0.005;
    ssaoPass.maxDistance = 0.05;
    ssaoPass.output = 0; // 默认输出
    composer.addPass(ssaoPass);
    ssaoPassRef.current = ssaoPass;
    
    // Bloom Pass - 让高光和雪山发光
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(width, height),
      0.3,   // strength（降低强度）
      0.5,   // radius  
      0.9    // threshold（提高阈值，只让最亮的地方发光）
    );
    composer.addPass(bloomPass);
    bloomPassRef.current = bloomPass;
    
    composerRef.current = composer;
    
    // 4. Render Loop
    let animationFrameId: number;
    let startTime = Date.now();
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      
      // 更新时间uniform（用于水面动画）
      const elapsedTime = (Date.now() - startTime) * 0.001;
      if (terrainMaterialRef.current) {
        terrainMaterialRef.current.uniforms.time.value = elapsedTime;
      }
      if (waterMaterialRef.current) {
        waterMaterialRef.current.uniforms.time.value = elapsedTime;
      }
      
      // 使用后处理或直接渲染
      if (enablePostProcessingRef.current && composerRef.current) {
        composerRef.current.render();
      } else {
        renderer.render(scene, camera);
      }
    };
    animate();

    const syncCameraFrustum = (cam: THREE.OrthographicCamera, viewportWidth: number, viewportHeight: number) => {
      const { viewWidth: nextWidth, viewHeight: nextHeight } = computeViewDimensions(viewportWidth, viewportHeight);
      cam.left = -nextWidth;
      cam.right = nextWidth;
      cam.top = nextHeight;
      cam.bottom = -nextHeight;
      cam.updateProjectionMatrix();
    };

    const getUnitsPerPixel = () => {
      if (!rendererRef.current || !cameraRef.current) {
        return { x: 1, y: 1 };
      }
      const dom = rendererRef.current.domElement;
      const viewWidthPx = dom.clientWidth || 1;
      const viewHeightPx = dom.clientHeight || 1;
      const cam = cameraRef.current;
      const worldWidth = (cam.right - cam.left) / cam.zoom;
      const worldHeight = (cam.top - cam.bottom) / cam.zoom;
      return {
        x: worldWidth / viewWidthPx,
        y: worldHeight / viewHeightPx,
      };
    };

    const panCameraByPixels = (dx: number, dy: number) => {
      const cam = cameraRef.current;
      if (!cam) return;
      const { x: unitX, y: unitY } = getUnitsPerPixel();
      // 反转X方向以匹配直觉的拖拽方向
      cam.position.x -= dx * unitX;
      cam.position.y += dy * unitY;
      cam.lookAt(cam.position.x, cam.position.y, 0);
    };

    const zoomCamera = (nextZoom: number, anchor?: { x: number; y: number }) => {
      const cam = cameraRef.current;
      const rendererInstance = rendererRef.current;
      if (!cam || !rendererInstance) return;
      const clamped = THREE.MathUtils.clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
      if (clamped === cam.zoom) return;
      const dom = rendererInstance.domElement;
      const rect = dom.getBoundingClientRect();
      const widthPx = rect.width || 1;
      const heightPx = rect.height || 1;

      const anchorX = anchor ? anchor.x - rect.left : widthPx / 2;
      const anchorY = anchor ? anchor.y - rect.top : heightPx / 2;

      const prevZoom = cam.zoom;
      const worldWidth = (cam.right - cam.left) / prevZoom;
      const worldHeight = (cam.top - cam.bottom) / prevZoom;
      const unitsPerPixelX = worldWidth / widthPx;
      const unitsPerPixelY = worldHeight / heightPx;

      const worldAnchorX = cam.position.x + (anchorX - widthPx / 2) * unitsPerPixelX;
      const worldAnchorY = cam.position.y - (anchorY - heightPx / 2) * unitsPerPixelY;

      const newWorldWidth = (cam.right - cam.left) / clamped;
      const newWorldHeight = (cam.top - cam.bottom) / clamped;
      const newUnitsPerPixelX = newWorldWidth / widthPx;
      const newUnitsPerPixelY = newWorldHeight / heightPx;

      cam.position.x = worldAnchorX - (anchorX - widthPx / 2) * newUnitsPerPixelX;
      cam.position.y = worldAnchorY + (anchorY - heightPx / 2) * newUnitsPerPixelY;
      cam.zoom = clamped;
      cam.updateProjectionMatrix();
      cam.lookAt(cam.position.x, cam.position.y, 0);
      setZoomLevel(clamped);
    };

    const createHighlight = (color: number, opacity: number, radiusScale: number) => {
      const baseRadius = (planeWidth / LOGIC_RES_X) * radiusScale;
      const geometry = new THREE.RingGeometry(baseRadius * 0.4, baseRadius, 48);
      const material = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.rotation.x = Math.PI / 2;
      mesh.visible = false;
      mesh.renderOrder = 10;
      scene.add(mesh);
      return mesh;
    };

    hoverHighlightRef.current = createHighlight(0xffff66, 0.8, 0.8);
    selectionHighlightRef.current = createHighlight(0xff8844, 0.6, 0.9);

    const dragState = {
      dragging: false,
      lastX: 0,
      lastY: 0,
      velocityX: 0,
      velocityY: 0,
      lastMoveTime: 0,
      inertiaId: null as number | null,
      startX: 0,
      startY: 0,
    };

    const performRaycast = (clientX: number, clientY: number): MapTileInfo | null => {
      if (!cameraRef.current || !terrainMeshRef.current || !rendererRef.current) return null;
      const rect = rendererRef.current.domElement.getBoundingClientRect();
      pointerRef.current.x = ((clientX - rect.left) / rect.width) * 2 - 1;
      pointerRef.current.y = -((clientY - rect.top) / rect.height) * 2 + 1;
      raycasterRef.current.setFromCamera(pointerRef.current, cameraRef.current);
      const intersects = raycasterRef.current.intersectObject(terrainMeshRef.current, false);
      if (intersects.length && intersects[0].uv) {
        const uv = intersects[0].uv;
        const logicX = Math.min(LOGIC_RES_X - 1, Math.max(0, Math.floor(uv.x * LOGIC_RES_X)));
        const logicY = Math.min(
          LOGIC_RES_Y - 1,
          Math.max(0, Math.floor((1 - uv.y) * LOGIC_RES_Y))
        );
        return getTileByLogicCoord(logicX, logicY);
      }
      return null;
    };

    const updateHoverTile = (event: MouseEvent) => {
      lastPointerRef.current = { clientX: event.clientX, clientY: event.clientY };
      const tile = performRaycast(event.clientX, event.clientY);
      hoverTileRef.current = tile;
      if (tile) {
        positionHighlight(hoverHighlightRef.current, tile, 9);
      } else {
        hideHighlight(hoverHighlightRef.current);
      }
    };

    const handleMouseLeave = () => {
      hoverTileRef.current = null;
      hideHighlight(hoverHighlightRef.current);
    };

    const stopInertia = () => {
      if (dragState.inertiaId !== null) {
        cancelAnimationFrame(dragState.inertiaId);
        dragState.inertiaId = null;
      }
    };

    const runInertia = () => {
      dragState.velocityX *= FRICTION;
      dragState.velocityY *= FRICTION;
      if (
        Math.abs(dragState.velocityX) < STOP_VELOCITY &&
        Math.abs(dragState.velocityY) < STOP_VELOCITY
      ) {
        dragState.inertiaId = null;
        return;
      }
      panCameraByPixels(dragState.velocityX, dragState.velocityY);
      dragState.inertiaId = requestAnimationFrame(runInertia);
    };

    const canvas = renderer.domElement;

    const handleMouseDown = (event: MouseEvent) => {
      if (event.button !== 0) return;
      dragState.dragging = true;
      dragState.lastX = event.clientX;
      dragState.lastY = event.clientY;
      dragState.startX = event.clientX;
      dragState.startY = event.clientY;
      dragState.velocityX = 0;
      dragState.velocityY = 0;
      dragState.lastMoveTime = performance.now();
      stopInertia();
      canvas.style.cursor = "grabbing";
      updateHoverTile(event);
    };

    const handleMouseMove = (event: MouseEvent) => {
      if (!dragState.dragging) return;
      const dx = event.clientX - dragState.lastX;
      const dy = event.clientY - dragState.lastY;
      dragState.lastX = event.clientX;
      dragState.lastY = event.clientY;
      if (dx === 0 && dy === 0) return;
      panCameraByPixels(dx, dy);
      dragState.velocityX = dx;
      dragState.velocityY = dy;
      dragState.lastMoveTime = performance.now();
      updateHoverTile(event);
    };

    const handleMouseUp = (event: MouseEvent) => {
      if (!dragState.dragging) return;
      dragState.dragging = false;
      canvas.style.cursor = "grab";
      const elapsed = performance.now() - dragState.lastMoveTime;
      if (elapsed < 120 && (Math.abs(dragState.velocityX) > 0.5 || Math.abs(dragState.velocityY) > 0.5)) {
        stopInertia();
        dragState.inertiaId = requestAnimationFrame(runInertia);
      }

      const moved = Math.hypot(event.clientX - dragState.startX, event.clientY - dragState.startY);
      if (moved < 6) {
        const tile = hoverTileRef.current;
        if (tile) {
          positionHighlight(selectionHighlightRef.current, tile, 11);
          const pointer = lastPointerRef.current ?? { clientX: event.clientX, clientY: event.clientY };
          onSelectTile(tile, pointer);
        }
      }
    };

    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      const delta = event.deltaY > 0 ? -0.15 : 0.15;
      zoomCamera((cameraRef.current?.zoom || 1) + delta, { x: event.clientX, y: event.clientY });
    };

    const handleResize = () => {
        if (!containerRef.current || !rendererRef.current || !cameraRef.current) return;
        const newWidth = containerRef.current.clientWidth;
        const newHeight = containerRef.current.clientHeight;
        rendererRef.current.setSize(newWidth, newHeight);
        composerRef.current?.setSize(newWidth, newHeight);
        ssaoPassRef.current?.setSize(newWidth, newHeight);
        bloomPassRef.current?.setSize(newWidth, newHeight);
        syncCameraFrustum(cameraRef.current, newWidth, newHeight);
    };

    canvas.addEventListener("mousedown", handleMouseDown);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    canvas.addEventListener("wheel", handleWheel, { passive: false });
    canvas.addEventListener("mousemove", updateHoverTile);
    canvas.addEventListener("mouseleave", handleMouseLeave);
    window.addEventListener("resize", handleResize);

    controlsRef.current = {
      zoomBy: (delta: number) => {
        zoomCamera((cameraRef.current?.zoom || 1) + delta);
      },
      reset: () => {
        if (!cameraRef.current) return;
        stopInertia();
        cameraRef.current.position.set(0, 0, 1000);
        cameraRef.current.lookAt(0, 0, 0);
        cameraRef.current.zoom = 1;
        cameraRef.current.updateProjectionMatrix();
        setZoomLevel(1);
      },
    };

    // 4. Fetch Data and Create Materials
    let disposed = false;

    const loadData = async () => {
      try {
        if (disposed) return;
        setLoading(true);
        setError(null);
        
        console.log("Fetching GPU Map Data...");
        const [heightData, waterData, erosionData] = await Promise.all([
          fetchHeightMap(),
          fetchWaterMask(),
          fetchErosionMap()
        ]);
        if (disposed) return;
        
        const expectedSamples = PHYSICS_RES_X * PHYSICS_RES_Y;
        console.log(`Received Data: Height=${heightData.length}, Water=${waterData.length}, Erosion=${erosionData.length}, Expected=${expectedSamples}`);

        if (
            heightData.length === expectedSamples &&
            waterData.length === expectedSamples &&
            erosionData.length === expectedSamples * 2
        ) {
            // 检查数据是否全为0
            const heightSum = heightData.reduce((sum, val) => sum + Math.abs(val), 0);
            if (heightSum < 1.0) {
                setError("3D地图数据为空，请先创建或加载存档以生成地形数据");
                setLoading(false);
                return;
            }
            
            const heightMin = heightData.reduce((min, v) => Math.min(min, v), Infinity);
            const heightMax = heightData.reduce((max, v) => Math.max(max, v), -Infinity);
            console.log(`✅ 3D地图数据加载成功: ${heightMin.toFixed(1)}m ~ ${heightMax.toFixed(1)}m`);
            
            // ============ 创建高度图纹理 ============
            // Three.js的DataTexture期望数据按行优先顺序排列
            // 后端发送的是 (2048, 640) 的数组，已经水平翻转
            const heightTexture = new THREE.DataTexture(
              heightData, 
              PHYSICS_RES_X,  // width
              PHYSICS_RES_Y,  // height
              THREE.RedFormat, 
              THREE.FloatType
            );
            heightTexture.minFilter = THREE.LinearFilter;
            heightTexture.magFilter = THREE.LinearFilter;
            heightTexture.wrapS = THREE.RepeatWrapping;  // 水平方向循环（地球环绕）
            heightTexture.wrapT = THREE.ClampToEdgeWrapping;  // 垂直方向夹紧（南北极）
            heightTexture.generateMipmaps = false;
            heightTexture.flipY = false;  // 不翻转Y轴
            heightTexture.needsUpdate = true;
            
            const waterTexture = new THREE.DataTexture(
              waterData, 
              PHYSICS_RES_X, 
              PHYSICS_RES_Y, 
              THREE.RedFormat, 
              THREE.FloatType
            );
            waterTexture.minFilter = THREE.LinearFilter;
            waterTexture.magFilter = THREE.LinearFilter;
            waterTexture.wrapS = THREE.RepeatWrapping;
            waterTexture.wrapT = THREE.ClampToEdgeWrapping;
            waterTexture.generateMipmaps = false;
            waterTexture.flipY = false;
            waterTexture.needsUpdate = true;

            const erosionTexture = new THREE.DataTexture(
              erosionData, 
              PHYSICS_RES_X, 
              PHYSICS_RES_Y, 
              THREE.RGFormat, 
              THREE.FloatType
            );
            erosionTexture.minFilter = THREE.LinearFilter;
            erosionTexture.magFilter = THREE.LinearFilter;
            erosionTexture.wrapS = THREE.RepeatWrapping;
            erosionTexture.wrapT = THREE.ClampToEdgeWrapping;
            erosionTexture.generateMipmaps = false;
            erosionTexture.flipY = false;
            erosionTexture.needsUpdate = true;

            // ============ 地形材质（增强版PBR Shader）============
            heightTextureRef.current?.dispose();
            waterTextureRef.current?.dispose();
            erosionTextureRef.current?.dispose();
            heightTextureRef.current = heightTexture;
            waterTextureRef.current = waterTexture;
            erosionTextureRef.current = erosionTexture;

            const terrainMaterial = new THREE.ShaderMaterial({
              vertexShader: terrainVertexShader,  // 使用增强shader
              fragmentShader: terrainFragmentShader,  // 使用增强shader
              uniforms: {
                heightMap: { value: heightTexture },
                erosionMap: { value: erosionTexture },
                scale: { value: 0.15 },
                resolution: { value: new THREE.Vector2(PHYSICS_RES_X, PHYSICS_RES_Y) },
                time: { value: 0.0 },
                detailAmplitude: { value: DETAIL_AMPLITUDE_METERS }
              },
              side: THREE.DoubleSide
            });

            // ============ 水体材质（分离渲染）============
            const waterMaterial = new THREE.ShaderMaterial({
              vertexShader: waterVertexShader,
              fragmentShader: waterFragmentShader,
              uniforms: {
                heightMap: { value: heightTexture },
                waterMask: { value: waterTexture },
                erosionMap: { value: erosionTexture },
                scale: { value: 0.05 },
                time: { value: 0.0 }
              },
              transparent: true,
              side: THREE.FrontSide,
              depthWrite: false, // 水面不写入深度，避免遮挡问题
              blending: THREE.NormalBlending
            });

            // ============ 创建地形Mesh ============
            const terrainMesh = new THREE.Mesh(geometry, terrainMaterial);
            scene.add(terrainMesh);
            terrainMeshRef.current = terrainMesh;
            
            // ============ 创建水体Mesh ============
            const waterGeometry = new THREE.PlaneGeometry(planeWidth, planeHeight, segmentsX / 2, segmentsY / 2);
            waterGeometryRef.current = waterGeometry;
            const waterMesh = new THREE.Mesh(waterGeometry, waterMaterial);
            waterMesh.position.z = 0.5; // 略微抬高，位于地形之上
            scene.add(waterMesh);
            waterMeshRef.current = waterMesh;
            
            terrainMaterialRef.current = terrainMaterial;
            waterMaterialRef.current = waterMaterial;
            
            console.log("✅ 增强版3D地图渲染完成！");
            console.log(`   - 地形: PBR材质 + Triplanar贴图 + 环境光遮蔽`);
            console.log(`   - 水体: 动态波浪 + Fresnel反射 + 岸线泡沫`);
            console.log(`   - 后处理: SSAO + Bloom`);
            
            // 成功加载，清除错误和加载状态
            if (!disposed) {
              setError(null);
              setLoading(false);
            }
        } else {
             console.error("Map data size mismatch");
             if (!disposed) {
               setError(`地图数据尺寸不匹配: 高度=${heightData.length}, 水体=${waterData.length}, 侵蚀=${erosionData.length}, 期望=${expectedSamples}/${expectedSamples}/${expectedSamples * 2}`);
               setLoading(false);
             }
        }
      } catch (e: any) {
        console.error("Failed to load map data", e);
        if (disposed) return;
        // 检查是否是503错误（服务不可用）
        if (e.message && e.message.includes("heightmap fetch failed")) {
          setError("3D地图未就绪：请先创建或加载存档以生成地形数据");
        } else {
          setError(`加载3D地图数据失败: ${e.message || "未知错误"}`);
        }
        setLoading(false);
      }
    };

    // 初始加载数据
    loadData();

    // Cleanup
    return () => {
      disposed = true;
      stopInertia();
      cancelAnimationFrame(animationFrameId);
      canvas.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      canvas.removeEventListener("wheel", handleWheel);
      canvas.removeEventListener("mousemove", updateHoverTile);
      canvas.removeEventListener("mouseleave", handleMouseLeave);
      window.removeEventListener("resize", handleResize);
      composerRef.current?.dispose();
      composerRef.current = null;
      ssaoPassRef.current = null;
      bloomPassRef.current = null;
      if (terrainMeshRef.current) {
        scene.remove(terrainMeshRef.current);
        terrainMeshRef.current = null;
      }
      if (waterMeshRef.current) {
        scene.remove(waterMeshRef.current);
        waterMeshRef.current = null;
      }
      terrainGeometryRef.current?.dispose();
      terrainGeometryRef.current = null;
      waterGeometryRef.current?.dispose();
      waterGeometryRef.current = null;
      renderer.dispose();
      rendererRef.current = null;
      cameraRef.current = null;
      sceneRef.current = null;
      terrainMaterialRef.current?.dispose();
      terrainMaterialRef.current = null;
      waterMaterialRef.current?.dispose();
      waterMaterialRef.current = null;
      heightTextureRef.current?.dispose();
      heightTextureRef.current = null;
      waterTextureRef.current?.dispose();
      waterTextureRef.current = null;
      erosionTextureRef.current?.dispose();
      erosionTextureRef.current = null;
      if (hoverHighlightRef.current) {
        hoverHighlightRef.current.geometry.dispose();
        (hoverHighlightRef.current.material as THREE.Material).dispose();
        scene.remove(hoverHighlightRef.current);
        hoverHighlightRef.current = null;
      }
      if (selectionHighlightRef.current) {
        selectionHighlightRef.current.geometry.dispose();
        (selectionHighlightRef.current.material as THREE.Material).dispose();
        scene.remove(selectionHighlightRef.current);
        selectionHighlightRef.current = null;
      }
      if (containerRef.current) {
        containerRef.current.removeChild(renderer.domElement);
      }
    };
  }, []);

  // 当dataVersion变化时重新加载地图数据
  useEffect(() => {
    if (dataVersion > 0 && terrainMaterialRef.current) {
      const reloadData = async () => {
        try {
          setLoading(true);
          console.log('[3D Map] Reloading heightmap data...');
          
          const [heightData, waterData, erosionData] = await Promise.all([
            fetchHeightMap(),
            fetchWaterMask(),
            fetchErosionMap()
          ]);

          const expectedSamples = PHYSICS_RES_X * PHYSICS_RES_Y;
          if (
            heightData.length !== expectedSamples ||
            waterData.length !== expectedSamples ||
            erosionData.length !== expectedSamples * 2
          ) {
            console.error('[3D Map] Invalid data size on reload');
            setLoading(false);
            return;
          }

          const heightMin = heightData.reduce((min, v) => Math.min(min, v), Infinity);
          const heightMax = heightData.reduce((max, v) => Math.max(max, v), -Infinity);
          console.log(`✅ 3D地图数据重新加载: ${heightMin.toFixed(1)}m ~ ${heightMax.toFixed(1)}m`);

          // 更新纹理数据
          const heightTexture = new THREE.DataTexture(
            heightData,
            PHYSICS_RES_X,
            PHYSICS_RES_Y,
            THREE.RedFormat,
            THREE.FloatType
          );
          heightTexture.minFilter = THREE.LinearFilter;
          heightTexture.magFilter = THREE.LinearFilter;
          heightTexture.wrapS = THREE.RepeatWrapping;
          heightTexture.wrapT = THREE.ClampToEdgeWrapping;
          heightTexture.flipY = false;
          heightTexture.needsUpdate = true;

          const waterTexture = new THREE.DataTexture(
            waterData,
            PHYSICS_RES_X,
            PHYSICS_RES_Y,
            THREE.RedFormat,
            THREE.FloatType
          );
          waterTexture.minFilter = THREE.LinearFilter;
          waterTexture.magFilter = THREE.LinearFilter;
          waterTexture.wrapS = THREE.RepeatWrapping;
          waterTexture.wrapT = THREE.ClampToEdgeWrapping;
          waterTexture.flipY = false;
          waterTexture.needsUpdate = true;

          const erosionTexture = new THREE.DataTexture(
            erosionData,
            PHYSICS_RES_X,
            PHYSICS_RES_Y,
            THREE.RGFormat,
            THREE.FloatType
          );
          erosionTexture.minFilter = THREE.LinearFilter;
          erosionTexture.magFilter = THREE.LinearFilter;
          erosionTexture.wrapS = THREE.RepeatWrapping;
          erosionTexture.wrapT = THREE.ClampToEdgeWrapping;
          erosionTexture.flipY = false;
          erosionTexture.needsUpdate = true;

          // 更新材质的纹理
          heightTextureRef.current?.dispose();
          waterTextureRef.current?.dispose();
          erosionTextureRef.current?.dispose();
          heightTextureRef.current = heightTexture;
          waterTextureRef.current = waterTexture;
          erosionTextureRef.current = erosionTexture;

          if (terrainMaterialRef.current) {
            terrainMaterialRef.current.uniforms.heightMap.value = heightTexture;
            terrainMaterialRef.current.uniforms.erosionMap.value = erosionTexture;
            terrainMaterialRef.current.uniformsNeedUpdate = true;
          }
          
          if (waterMaterialRef.current) {
            waterMaterialRef.current.uniforms.heightMap.value = heightTexture;
            waterMaterialRef.current.uniforms.waterMask.value = waterTexture;
            waterMaterialRef.current.uniforms.erosionMap.value = erosionTexture;
            waterMaterialRef.current.uniformsNeedUpdate = true;
          }

          console.log('✅ 3D地图纹理已更新！');
          setLoading(false);
        } catch (e: any) {
          console.error('[3D Map] Failed to reload data:', e);
          setLoading(false);
        }
      };
      
      reloadData();
    }
  }, [dataVersion]);

  useEffect(() => {
    if (selectedTile) {
      positionHighlight(selectionHighlightRef.current, selectedTile, 11);
    } else {
      hideHighlight(selectionHighlightRef.current);
    }
  }, [selectedTile]);

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%", position: "relative" }}>
      {loading && !error && (
        <div style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          color: "white",
          background: "rgba(0,0,0,0.7)",
          padding: "20px",
          borderRadius: "8px",
          zIndex: 10
        }}>
          正在加载3D地图数据...
        </div>
      )}
      {error && !loading && (
        <div style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          color: "#ff6b6b",
          background: "rgba(0,0,0,0.85)",
          padding: "20px",
          borderRadius: "8px",
          maxWidth: "400px",
          textAlign: "center",
          zIndex: 10
        }}>
          <div style={{ fontSize: "18px", marginBottom: "10px" }}>⚠️ 无法显示3D地图</div>
          <div style={{ fontSize: "14px", color: "#ccc" }}>{error}</div>
          <button 
            onClick={handleManualRefresh}
            style={{
              marginTop: "15px",
              padding: "8px 16px",
              background: "#4a9eff",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer"
            }}
          >
            刷新重试
          </button>
        </div>
      )}
      {!loading && !error && (
        <>
          <div className="map-zoom-controls">
            <div className="zoom-group">
              <button type="button" onClick={() => controlsRef.current.zoomBy(0.15)} title="放大">＋</button>
              <button type="button" onClick={() => controlsRef.current.zoomBy(-0.15)} title="缩小">－</button>
            </div>
            <button type="button" className="zoom-reset" title="重置视角" onClick={() => controlsRef.current.reset()}>
              {Math.round(zoomLevel * 100)}%
            </button>
          </div>
          
          <div style={{
            position: "absolute",
            bottom: "20px",
            left: "20px",
            background: "rgba(0,0,0,0.7)",
            padding: "12px 16px",
            borderRadius: "6px",
            color: "white",
            fontSize: "13px",
            display: "flex",
            alignItems: "center",
            gap: "12px",
            flexWrap: "wrap",
            zIndex: 10
          }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: "140px" }}>
              <span>当前视图：{viewModeLabel}</span>
              <span>高亮物种：{highlightedSpeciesLabel}</span>
            </div>
            <button
              type="button"
              onClick={handleViewModeShortcut}
              style={{
                padding: "6px 12px",
                background: "rgba(74,158,255,0.25)",
                border: "1px solid rgba(74,158,255,0.6)",
                borderRadius: "4px",
                color: "white",
                cursor: "pointer"
              }}
            >
              {viewModeShortcutLabel}
            </button>
            <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
              <input 
                type="checkbox" 
                checked={enablePostProcessing}
                onChange={(e) => setEnablePostProcessing(e.target.checked)}
              />
              <span>后处理效果 (SSAO + Bloom)</span>
            </label>
          </div>
        </>
      )}
    </div>
  );
};


<template>
  <div class="block box">
    <p class="level title is-5">
      <span class="level-left">{{ TYPES[type] }}</span>
      <b-icon class="level-right" type="is-danger" icon="trash" @click.stop="$emit('remove')" />
    </p>
    <b-field label-position="inside" label="Type">
      <b-select v-model="type" expanded placeholder="Select a smartmeter">
        <option v-for="(name, typeKey) in TYPES" :value="typeKey" :key="typeKey">{{ name }}</option>
      </b-select>
    </b-field>
    <b-field v-if="customPort" label-position="inside" label="Port/Device">
      <b-input v-model="port" type="text" required placeholder="/dev/ttyUSB0" lazy></b-input>
    </b-field>
    <b-field v-else grouped label-position="inside" label="TTY USB Devices">
      <b-select v-model="port" expanded>
        <option v-for="port in availablePorts" :value="port" :key="port">{{ port }}</option>
      </b-select>
      <b-button icon-right="sync-alt" @click="loadPorts" />
    </b-field>
    <b-field>
      <b-checkbox v-model="customPort">Enter custom port</b-checkbox>
    </b-field>
    <b-field label-position="inside" label="Decryption Key (optional)">
      <b-input v-model="key" type="text" lazy></b-input>
    </b-field>

    <b-field>
      <b-checkbox v-model="showAdvanced">Custom scaling &amp; units (optional)</b-checkbox>
    </b-field>
    <b-collapse v-model="showAdvanced" animation="slide">
      <div class="box">
        <p class="is-size-7 mb-3">
          All fields are optional and applied on top of the meter's built-in behaviour. Leaving them empty keeps the
          default values and units. Scaling and unit conversion are multiplied together; per-OBIS entries override the
          global / per-unit ones.
        </p>

        <b-field label-position="inside" label="Global scaling factor">
          <b-input v-model="scale" type="number" placeholder="1.0" lazy></b-input>
        </b-field>

        <label class="label is-small">Scaling per OBIS code</label>
        <b-field v-for="(row, i) in scaleRows" :key="'s' + i" grouped>
          <b-input v-model="row.obis" placeholder="e.g. 1.0.3.7.0" expanded lazy></b-input>
          <p class="is-align-self-center">scaled with</p>
          <b-input v-model="row.factor" type="number" placeholder="1.0" lazy></b-input>
          <b-button type="is-danger is-light is-small" icon-right="trash" @click="scaleRows.splice(i, 1)" />
        </b-field>
        <b-button class="mb-4" size="is-small" icon-left="plus" @click="scaleRows.push({ obis: '', factor: '' })">
          Add OBIS scaling
        </b-button>

        <label class="label is-small">Unit conversion per measurement</label>
        <b-field v-for="(row, i) in unitClassRows" :key="'uc' + i" grouped>
          <b-select v-model="row.unit" expanded placeholder="from unit">
            <option v-for="u in UNIT_CLASSES" :value="u" :key="u">{{ u }}</option>
          </b-select>
          <p class="is-align-self-center">to unit</p>
          <b-input v-model="row.target" placeholder="e.g. kW" expanded lazy></b-input>
          <b-button type="is-danger is-light is-small" icon-right="trash" @click="unitClassRows.splice(i, 1)" />
        </b-field>
        <b-button class="mb-4" size="is-small" icon-left="plus" @click="unitClassRows.push({ unit: 'W', target: '' })">
          Add unit conversion
        </b-button>

        <label class="label is-small">Unit conversion per OBIS code</label>
        <b-field v-for="(row, i) in unitObisRows" :key="'uo' + i" grouped>
          <b-input v-model="row.obis" placeholder="e.g. 1.0.3.7.0" expanded lazy></b-input>
          <p class="is-align-self-center">to unit</p>
          <b-input v-model="row.target" placeholder="e.g. kvar" expanded lazy></b-input>
          <b-button type="is-danger is-light is-small" icon-right="trash" @click="unitObisRows.splice(i, 1)" />
        </b-field>
        <b-button size="is-small" icon-left="plus" @click="unitObisRows.push({ obis: '', target: '' })">
          Add OBIS unit override
        </b-button>
      </div>
    </b-collapse>
  </div>
</template>

<script>
import { getTtyDevices } from "../api";
export default {
  props: {
    initConfig: {
      type: Object,
      require: true,
    },
  },
  data() {
    return {
      id: this.initConfig.id,
      type: this.initConfig.type || "lge450",
      port: this.initConfig.port || "",
      key: this.initConfig.key || "",
      availablePorts: this.loadPorts(),
      customPort: false,
      scale: this.initConfig.scale != null ? this.initConfig.scale : "",
      scaleRows: Object.entries(this.initConfig.scale_per_obis || {}).map(([obis, factor]) => ({ obis, factor })),
      unitClassRows: Object.entries(this.initConfig.unit_per_class || {}).map(([unit, target]) => ({ unit, target })),
      unitObisRows: Object.entries(this.initConfig.unit_per_obis || {}).map(([obis, target]) => ({ obis, target })),
      showAdvanced: false,
    };
  },
  created() {
    this.TYPES = {
      lge450: "L+G E450",
      lge360: "L+G E360",
      lge570: "L+G E570",
      iskraam550: "Iskraemeco AM550",
      kamstrup_han: "Kamstrup HAN",
    };
    this.UNIT_CLASSES = ["W", "Wh", "VA", "VAh", "V", "A"];
  },
  computed: {
    config() {
      const scalePerObis = {};
      this.scaleRows.forEach((row) => {
        if (row.obis && row.factor !== "" && row.factor !== null) {
          scalePerObis[row.obis.trim()] = Number(row.factor);
        }
      });
      const unitPerClass = {};
      this.unitClassRows.forEach((row) => {
        if (row.unit && row.target) {
          unitPerClass[row.unit] = row.target.trim();
        }
      });
      const unitPerObis = {};
      this.unitObisRows.forEach((row) => {
        if (row.obis && row.target) {
          unitPerObis[row.obis.trim()] = row.target.trim();
        }
      });
      return {
        type: this.type,
        port: this.port,
        key: this.key || null,
        scale: this.scale === "" || this.scale === null ? null : Number(this.scale),
        scale_per_obis: scalePerObis,
        unit_per_class: unitPerClass,
        unit_per_obis: unitPerObis,
      };
    },
  },
  watch: {
    config: {
      handler(value) {
        this.$emit("update", value);
      },
      immediate: true,
    },
  },
  methods: {
    loadPorts() {
      getTtyDevices()
        .then((devices) => {
          this.availablePorts = devices;
        })
        .catch(() => {
          this.$buefy.toast.open({
            message: "Unable to retrieve available ports.",
            type: "is-danger",
            position: "is-top",
            duration: 4000,
          });
          this.availablePorts = [];
        });
    },
  },
};
</script>

<style scoped></style>

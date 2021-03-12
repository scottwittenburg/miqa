<script>
import { mapActions, mapMutations } from "vuex";

export default {
  name: "DataImportExport",
  components: {},
  inject: ["girderRest"],
  data: () => ({
    importEnabled: false,
    exportEnabled: false,
    importing: false,
    importDialog: false,
    loadDialog: false,
    loading: false,
    loadFiles: [],
    localExperimentId: "",
    localScanId: "",
    localScanType: "",
    knownScanTypes: [
      "dti30b400",
      "grefieldmap",
      "grefieldmap",
      "rsfmri",
      "t2fse",
      "mprage",
      "dti6b500pepolar",
      "dti60b1001"
    ]
  }),
  async created() {
    var { data: result } = await this.girderRest.get(
      "miqa_setting/import-export-enabled"
    );
    this.importEnabled = result.import;
    this.exportEnabled = result.export;
  },
  methods: {
    ...mapActions(["loadSessions"]),
    ...mapMutations(["addLocalScan"]),
    async importData() {
      this.importing = true;
      try {
        var { data: result } = await this.girderRest.post("miqa/data/import");
        this.importing = false;
        this.$snackbar({
          text: `Import finished.
          With ${result.success} scans succeeded and ${result.failed} failed.`,
          timeout: 6000
        });
        this.loadSessions();
      } catch (ex) {
        this.importing = false;
        this.$snackbar({
          text: "Import failed. Refer console for detail."
        });
        console.error(ex.response);
      }
      this.importDialog = false;
    },
    async loadData() {
      this.loadFiles.forEach(file => {
        console.log(`  ${file.name}`);
      });

      const localScanData = {
        files: this.loadFiles.map(f => f),
        experimentId: this.localExperimentId,
        scanId: this.localScanId,
        scanType: this.localScanType
      };

      this.addLocalScan(localScanData);

      this.loadDialog = false;
    },
    async exportData() {
      await this.girderRest.get("miqa/data/export");
      this.$prompt({
        title: "Export",
        text: "Saved data to file successfully.",
        positiveButton: "Ok"
      });
    }
  }
};
</script>

<template>
  <div>
    <v-btn
      text
      color="primary"
      @click="importDialog = true"
      :disabled="!importEnabled"
      >Import</v-btn
    >
    <v-btn
      text
      color="primary"
      @click="loadDialog = true"
      :disabled="!importEnabled"
    >
      Load
    </v-btn>
    <v-btn text color="primary" @click="exportData" :disabled="!exportEnabled"
      >Export</v-btn
    >
    <v-dialog v-model="importDialog" width="500" :persistent="importing">
      <v-card>
        <v-card-title class="title">
          Import
        </v-card-title>
        <v-card-text>
          Import data would delete outdated records from the system, do you want
          to continue?
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn text @click="importDialog = false" :disabled="importing"
            >Cancel</v-btn
          >
          <v-btn text color="primary" @click="importData" :loading="importing"
            >Import</v-btn
          >
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-dialog v-model="loadDialog" width="500">
      <v-card>
        <v-card-title class="title">
          Load a scan
        </v-card-title>
        <v-card-text>
          <v-container>
            <v-row>
              <v-col cols="12">
                <v-file-input
                  v-model="loadFiles"
                  chips
                  multiple
                  label="Image files"
                ></v-file-input>
              </v-col>
            </v-row>
            <v-row>
              <v-col cols="12">
                <v-text-field
                  v-model="localExperimentId"
                  label="Experiment ID"
                ></v-text-field>
              </v-col>
            </v-row>
            <v-row>
              <v-col cols="12">
                <v-text-field
                  v-model="localScanId"
                  label="Scan ID"
                ></v-text-field>
              </v-col>
            </v-row>
            <v-row>
              <v-col cols="12">
                <v-select
                  v-model="localScanType"
                  :items="knownScanTypes"
                  label="Scan Type"
                ></v-select>
              </v-col>
            </v-row>
          </v-container>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn text @click="loadDialog = false">Cancel</v-btn>
          <v-btn text color="primary" @click="loadData">Load</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style lang="scss" scoped></style>

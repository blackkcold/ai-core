plugins {
    kotlin("jvm") version "2.2.20"
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.json:json:20240303")
}

kotlin {
    jvmToolchain(17)
    sourceSets {
        main {
            kotlin.srcDir(".")
            kotlin.exclude("build/**")
        }
    }
}

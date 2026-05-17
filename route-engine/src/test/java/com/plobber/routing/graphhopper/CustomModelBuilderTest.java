package com.plobber.routing.graphhopper;

import com.graphhopper.json.Statement;
import com.graphhopper.util.CustomModel;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class CustomModelBuilderTest {

    @Test
    @DisplayName("PLOGGING 모드: 7단계 trash_prob 기반 priority 분기가 존재해야 한다.")
    void buildPloggingModel_hasGranularTrashProbTiers() {
        // given
        CustomModelBuilder builder = new CustomModelBuilder();

        // when
        CustomModel model = builder.build("PLOGGING");

        // then
        List<Statement> priorities = model.getPriority();
        assertThat(priorities).isNotEmpty();

        assertThat(priorities.stream()
                .anyMatch(s -> s.condition() != null && s.condition().contains("trash_prob >= 0.95")))
                .as("0.95 이상 최고 핫스팟 tier 존재")
                .isTrue();

        assertThat(priorities.stream()
                .anyMatch(s -> s.condition() != null && s.condition().contains("trash_prob >= 0.9")))
                .as("0.9 이상 고확률 tier 존재")
                .isTrue();

        assertThat(priorities.stream()
                .anyMatch(s -> s.condition() != null && s.condition().contains("trash_prob >= 0.7")))
                .as("0.7 이상 tier 존재")
                .isTrue();
    }

    @Test
    @DisplayName("PLOGGING 모드: 고확률 도로에 multiply_by > 1.0 보너스가 적용되어야 한다.")
    void buildPloggingModel_hasBoostForHighTrashProb() {
        // given
        CustomModelBuilder builder = new CustomModelBuilder();

        // when
        CustomModel model = builder.build("PLOGGING");

        // then
        List<Statement> priorities = model.getPriority();

        boolean hasBoost = priorities.stream()
                .anyMatch(s -> s.condition() != null
                        && s.condition().contains("trash_prob >= 0.95")
                        && s.value().contains("2.5"));
        assertThat(hasBoost)
                .as("trash_prob >= 0.95 도로에 multiply_by 2.5 보너스")
                .isTrue();
    }

    @Test
    @DisplayName("PLOGGING 모드: distance_influence가 30.0이어야 한다.")
    void buildPloggingModel_distanceInfluence30() {
        // given
        CustomModelBuilder builder = new CustomModelBuilder();

        // when
        CustomModel model = builder.build("PLOGGING");

        // then
        assertThat(model.getDistanceInfluence()).isEqualTo(30.0);
    }

    @Test
    @DisplayName("PLOGGING 모드: 대로 회피 규칙이 존재해야 한다.")
    void buildPloggingModel_avoidsMainRoads() {
        // given
        CustomModelBuilder builder = new CustomModelBuilder();

        // when
        CustomModel model = builder.build("PLOGGING");

        // then
        boolean hasRoadClassCondition = model.getPriority().stream()
                .anyMatch(s -> s.condition() != null && s.condition().contains("road_class == PRIMARY"));
        assertThat(hasRoadClassCondition).isTrue();
    }

    @Test
    @DisplayName("COMFORT 모드: 쓰레기 확률이 높은 길을 회피하는 CustomModel이 반환되어야 한다.")
    void buildComfortModelTest() {
        // given
        CustomModelBuilder builder = new CustomModelBuilder();

        // when
        CustomModel model = builder.build("COMFORT");

        // then
        assertThat(model).isNotNull();
        List<Statement> priorities = model.getPriority();
        assertThat(priorities).isNotEmpty();

        boolean hasTrashProbCondition = priorities.stream()
                .anyMatch(s -> s.condition() != null && s.condition().contains("trash_prob > 0.8"));
        assertThat(hasTrashProbCondition).isTrue();
        assertThat(model.getDistanceInfluence()).isEqualTo(70.0);
    }

    @Test
    @DisplayName("알 수 없는 모드를 요청할 경우 기본 CustomModel을 반환해야 한다.")
    void buildDefaultModelTest() {
        // given
        CustomModelBuilder builder = new CustomModelBuilder();

        // when
        CustomModel model = builder.build("UNKNOWN_MODE");

        // then
        assertThat(model).isNotNull();
        assertThat(model.getPriority()).isEmpty();
    }
}

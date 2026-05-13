package com.plobber.routing.graphhopper;

import com.graphhopper.json.Statement;
import com.graphhopper.util.CustomModel;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class CustomModelBuilderTest {

    @Test
    @DisplayName("플로깅 모드(PLOGGING) 요청 시 쓰레기 확률이 높은 길의 우선순위를 높여주는 CustomModel이 반환되어야 한다.")
    void buildPloggingModelTest() {
        // given
        CustomModelBuilder builder = new CustomModelBuilder();

        // when
        CustomModel model = builder.build("PLOGGING");

        // then
        assertThat(model).isNotNull();
        List<Statement> priorities = model.getPriority();
        assertThat(priorities).isNotEmpty();

        boolean hasTrashProbCondition = priorities.stream()
                .anyMatch(stmt -> stmt.condition() != null && stmt.condition().contains("trash_prob < 0.3"));
        assertThat(hasTrashProbCondition).isTrue();

        boolean hasRoadClassCondition = priorities.stream()
                .anyMatch(stmt -> stmt.condition() != null && stmt.condition().contains("road_class == PRIMARY"));
        assertThat(hasRoadClassCondition).isTrue();
        assertThat(model.getDistanceInfluence()).isEqualTo(50.0);
    }

    @Test
    @DisplayName("산책 모드(COMFORT) 요청 시 쓰레기 확률이 높은 길을 회피하는 CustomModel이 반환되어야 한다.")
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
                .anyMatch(stmt -> stmt.condition() != null && stmt.condition().contains("trash_prob > 0.8"));
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

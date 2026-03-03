/*
Copyright 2021 The KServe Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package components

import (
	"testing"

	"github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"github.com/kserve/kserve/pkg/apis/serving/v1alpha1"
	"github.com/kserve/kserve/pkg/apis/serving/v1beta1"
	"github.com/kserve/kserve/pkg/constants"
)

func TestPopulateProtocolStatus(t *testing.T) {
	g := gomega.NewGomegaWithT(t)
	protocolV2 := constants.ProtocolV2

	tests := []struct {
		name                       string
		isvc                       *v1beta1.InferenceService
		sRuntime                   v1alpha1.ServingRuntimeSpec
		expectedSupportedProtocols []constants.InferenceServiceProtocol
		expectedModelName          string
	}{
		{
			name: "runtime with multiple protocols",
			isvc: &v1beta1.InferenceService{
				ObjectMeta: metav1.ObjectMeta{Name: "my-model", Namespace: "default"},
				Spec: v1beta1.InferenceServiceSpec{
					Predictor: v1beta1.PredictorSpec{
						Model: &v1beta1.ModelSpec{
							PredictorExtensionSpec: v1beta1.PredictorExtensionSpec{
								ProtocolVersion: &protocolV2,
							},
						},
					},
				},
			},
			sRuntime: v1alpha1.ServingRuntimeSpec{
				ProtocolVersions: []constants.InferenceServiceProtocol{
					constants.ProtocolV1,
					constants.ProtocolV2,
					constants.ProtocolGRPCV2,
				},
			},
			expectedSupportedProtocols: []constants.InferenceServiceProtocol{
				constants.ProtocolV1,
				constants.ProtocolV2,
				constants.ProtocolGRPCV2,
			},
			expectedModelName: "my-model",
		},
		{
			name: "single protocol runtime",
			isvc: &v1beta1.InferenceService{
				ObjectMeta: metav1.ObjectMeta{Name: "sklearn-iris", Namespace: "default"},
				Spec: v1beta1.InferenceServiceSpec{
					Predictor: v1beta1.PredictorSpec{
						Model: &v1beta1.ModelSpec{},
					},
				},
			},
			sRuntime: v1alpha1.ServingRuntimeSpec{
				ProtocolVersions: []constants.InferenceServiceProtocol{
					constants.ProtocolV1,
				},
			},
			expectedSupportedProtocols: []constants.InferenceServiceProtocol{
				constants.ProtocolV1,
			},
			expectedModelName: "sklearn-iris",
		},
		{
			name: "runtime with rest and grpc protocols",
			isvc: &v1beta1.InferenceService{
				ObjectMeta: metav1.ObjectMeta{Name: "triton-model", Namespace: "default"},
				Spec: v1beta1.InferenceServiceSpec{
					Predictor: v1beta1.PredictorSpec{
						Model: &v1beta1.ModelSpec{},
					},
				},
			},
			sRuntime: v1alpha1.ServingRuntimeSpec{
				ProtocolVersions: []constants.InferenceServiceProtocol{
					constants.ProtocolV2,
					constants.ProtocolGRPCV2,
				},
			},
			expectedSupportedProtocols: []constants.InferenceServiceProtocol{
				constants.ProtocolV2,
				constants.ProtocolGRPCV2,
			},
			expectedModelName: "triton-model",
		},
		{
			name: "nil supported protocols from runtime",
			isvc: &v1beta1.InferenceService{
				ObjectMeta: metav1.ObjectMeta{Name: "custom-model", Namespace: "default"},
				Spec: v1beta1.InferenceServiceSpec{
					Predictor: v1beta1.PredictorSpec{
						Model: &v1beta1.ModelSpec{},
					},
				},
			},
			sRuntime: v1alpha1.ServingRuntimeSpec{
				ProtocolVersions: nil,
			},
			expectedSupportedProtocols: nil,
			expectedModelName:          "custom-model",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			p := &Predictor{}
			p.populateProtocolStatus(tt.isvc, tt.sRuntime)

			g.Expect(tt.isvc.Status.ModelStatus.SupportedProtocols).To(gomega.Equal(tt.expectedSupportedProtocols))
			g.Expect(tt.isvc.Status.ModelStatus.ModelName).To(gomega.Equal(tt.expectedModelName))
		})
	}
}

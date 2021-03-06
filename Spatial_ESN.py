import numpy as np
import random
import matplotlib as mpl
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.animation as animation
import scipy.spatial.distance as distance
from scipy.spatial import Voronoi,voronoi_plot_2d
import json
import time
import subprocess
from math import ceil,floor
import Bridson_sampling

# Default parameters
_data = {
    "seed"           : 21,
    "label_input" : "Mackey Glass",   #"Mackey Glass", "Sinus" or "Constant" in this case, else must be imported by hand (use the "input" variable name if you want to use the main())
    "display_animation" : False,
    "display_connectivity" : True,     # If the internal structure is displayed. Allows better understanding and checking.
    "savename" : "",             #The file where the animation is saved
    "number_neurons" : 400,
    "len_warmup" : 100,                #100,
    "len_training" : 1000,             #1000,
    "simulation_len" : 1000,
    "delays" : [i for i in range(100)],
    "delays" : [0],
    "external_sparsity" : 0.3,          #The probability of connection to the input/output (distance-based)
    "intern_sparsity" : 0.15,   #The probability of connection inside of the reservoir.
    "spectral_radius" : 1,
    "leak_rate" : 0.7,         #The greater it is, the more a neuron will lose its previous activity
    "epsilon" : 1e-8,
    "bin_size" : 0.05,
    "noise" : 0.001,
    "timestamp"      : "",
    "git_branch"     : "",
    "git_hash"       : "",
}


#----------------------------------------------------------------------------------------------------------------------

##Basic functions, used in this particular ESN class.
#Please note that since it is not a general application of ESN, they aren't modulable in this case
#And changes has to be done by hand in the class / by changing those functions under the same name in the file.
def sigmoid(x):
    return 1 / (1 + np.exp(-x))

def tanh(x):
    return np.tanh(x)

def generation_Bridson(number_points, k = 30, xmax = 1, ymax = 0.5):
    '''
    Generates a random sampling of point with blue noise properties.
    Uses the method described in Fast Poisson Disk Sampling in Arbitrary Dimensions, Robert Bridson
    Implementation by Nicolas Rougier, see Bridson_sampling.py file or https://www.labri.fr/perso/nrougier/from-python-to-numpy.

    :parameters:
        -number_points: the number of points we want generated. There will be an approximation of this number generated
        -min_dist: Minimum distance between two points. Analog to r
        -k: limit of samples to choose.
        -xmax, ymax: the rectangle in which the points are set in.
    :output:
        A numpy array of dimension (number_points,2) containing the points randomly generated
    '''
    optimal_radius =  np.sqrt((xmax * ymax)/(number_points*np.sqrt(3)))
    return Bridson_sampling.Bridson_sampling(width = xmax, height = ymax, radius = optimal_radius, k = k)


#----------------------------------------------------------------------------------------------------------------------

class Spatial_ESN:
    '''
    Notes that this is a specific Echo State Network for training purpose, without the maximum features.
    It may ultimately be a basic one for spatialisation purpose.
    '''
    def __init__(self,number_neurons, external_sparsity, intern_sparsity, number_input, number_output, spectral_radius, leak_rate, noise, isCopy = False):
        '''
        Creates an instance of spatial ESN given some parameters
        :parameters:
            - number_neurons : The number of neurons in the reservoir
            - external_sparsity: The probability to connect to the output/input from inside the reservoir.
            - intern_sparsity : Used for the connection in the spatial reservoir. The higher it is, the more connections there are.
            - number_input : How many input neurons.
            - number_output : How many output neurons.
            - spectral_radius : the desired spectral radius, depending on how lastong we want the memory to be.
            - leak_rate: The leak_rate on every update, symbolize the amount of information kept/lost.
            - isCopy: Boolean, False by default, defines wether we creating a copy or not. Shouldn't be used, except for method copy of Spatial_ESN.

        '''
        if not isCopy:
            print("---Creation of the Network---")
        self.number_input = number_input
        self.number_output = number_output
        self.N = number_neurons  #How many neurons in our reservoir
        self.leak_rate = leak_rate
        self.noise = noise
        self.isRecording = False
        self.external_sparsity = external_sparsity
        self.intern_sparsity = intern_sparsity
        self.spectral_radius = spectral_radius
        self.historic = []

        self.ymax = 0.5

        self.reset_reservoir(completeReset = not(isCopy))  #Sets the internal states and weight matrixes.

        #Values initialized later.
        self.len_warmup = -1
        self.len_training = -1
        if not isCopy:
            print("---Network Created---\n")

    def reset_reservoir(self,completeReset = False):
        '''
        Resets the values of the internal states. Warmup should be redone after a call to this function.
        :parameters:
            -completeReset,optional: Boolean, False by default, True will reset all the weights, used for (re)initialization. Network will need to be trained again in this case.
        '''
        if completeReset:
            print("---Beginning Blue Noise Sampling---")
            newpoints =  generation_Bridson(self.N,ymax = self.ymax)      #blueSampling(self.N)
            #We will have a number of neurons sligthly different from the expexted one, since the Bridson generation does not provide a fixed number of points.
            print("---Done---")

            self.N = newpoints.shape[0]  #Update to the actual number of neurons generated.

        self.x = np.zeros((self.N),dtype = [("activity",float),("position",float,(2,)),("mean",float)])
        self.x["activity"] = np.random.uniform(-1,1,(self.N,))   #Internal state of the reservoir. Initialisation might change

        self.x["mean"] = np.copy(self.x["activity"])

        self.istrained = False
        if completeReset:       #Initialization of the weights matrixes.

            self.n_iter = 0

            #The position of the neurons:
            #self.x["position"][:,0] = np.random.uniform(0,1,(self.N))
            #self.x["position"][:,1] = np.random.uniform(0,0.5,(self.N))
            self.x["position"] = newpoints

            self.W = np.random.uniform(-1,1,(self.N,self.N))  #The internal weight matrix
            distances = distance.cdist(self.x["position"],self.x["position"]) #Computes the distances between each nodes, used for the probability of connection.
            deltax = np.tile(self.x["position"][:,0],(self.N,1))
            deltax = (deltax.T - deltax)                                       #Checks if the x-distance is positive between 2 neurons

        #    self.W *= np.random.uniform(-1,1,self.W.shape) < self.external_sparsity * (1- np.eye(self.N))
            intern_connections = distances < np.random.uniform(0,self.intern_sparsity,(distances.shape))
            self.W *= intern_connections * (1-np.eye(self.N)) * (deltax > 0)   #Connects spatially


            self.W_in = np.random.uniform(-1,1,(self.N, 1 + self.number_input))    #We initialise between -1 and 1 uniformly, maybe to change. The added input will be the bias

            #self.W_in = np.ones((self.N, 1 + self.number_input)) #To better visualize, but to delete !
            connection_in = np.tile(self.x["position"][:,0],(self.number_input + 1,1)).T/(self.external_sparsity) < (np.random.uniform(0,1,self.W_in.shape))
            self.W_in *= connection_in

            self.W_out = np.random.uniform(-1,1,(self.N,self.number_output))
            #self.connection_out = np.tile(1-self.x["position"][:,0],(self. number_output,1)).T < (np.random.uniform(0,self.external_sparsity,self.W_out.shape))
            self.connection_out = (1-self.x["position"][:,0]) < (np.random.uniform(0,self.external_sparsity,self.N))  #The neurons connected to the output are connected to all of the exit neurons. (Makes the training easier)
            if self.number_output == 1:
                self.W_out *= np.tile(self.connection_out[np.newaxis].T,(self.number_output,1))
            else:
                self.W_out *= np.tile(self.connection_out,(self.number_output,1))


            #Spectral radius control:
            #A matrix taking into account the feedback from the output to the input, trying to imitate the echo state property.
            pseudo_W = self.W + (self.W_out @ self.W_in[:,1:].T).T     #This allows to have a non triangular matrix, giving a spectral radius different from 0.

            '''
            current_radius = np.max(np.abs(np.linalg.eigvals(pseudo_W)))

            if current_radius == 0.0:
                raise Exception("Null Spectral radius for generated matrix")
            else:
                #self.W *= self.spectral_radius/current_radius            #We normalize the weight matrix to get the desired spectral radius.
                pass
            '''
            self.W *= self.spectral_radius

            self.W_back = np.random.uniform(-1,1,(self.N,self.number_output))  #The Feedback matrix, not used in the test cases.
            self.y = np.zeros((self.number_output))

            norm = np.linalg.norm(self.W)
            print("Norm of W :" ,norm)
            print("Norm of W / number of connections in W : ",norm / np.sum(intern_connections) )

    def update(self,input = np.array([]) ,addNoise = False):
        '''
        Advance the process by 1 step, given some input if needed.
        '''
        if input.size == 0:
            input = np.zeros((self.number_input))
        else:
            input = np.array(input)
        u = np.concatenate((np.array([1.0]) , input + addNoise * self.generateNoise()))             #We add the bias.
        matrixA = np.dot(self.W_in, u)    #We put noise in the input if we are training.
        matrixB = np.dot(self.W , self.x["activity"])
        matrixC = 0 #self.W_back @ self.y #Feature deactivated and not tested in this particular case.
        self.x["activity"] = (1-self.leak_rate) * self.x["activity"] + self.leak_rate * tanh(matrixA + matrixB + matrixC )
        if np.isnan(np.sum(self.x["activity"])):    #Mostly for debugging purposes.
            raise Exception("Nan in matrix x : {} \n matrix y: {}".format(self.x["activity"],self.y))

        if self.isRecording:
            self.record_state()

        if self.istrained:
            self.y = np.dot(self.W_out,self.x["activity"])                     #We use a linear output (no postfunction treatment, should change training if one is added).

        self.n_iter +=1
        self.x["mean"] = (self.x["mean"] * self.n_iter + self.x["activity"]) / (self.n_iter + 1)

    def warmup(self,initial_inputs):
        """
        Proceeds with the initial warmup, given inputs.
        """
        print("---Beginning warmup---")
        for input in initial_inputs:
            self.update(input)  # Warmup period, should have an initialised reservoir at this point.
        print("---Warmup done---")

    def train(self,inputs,expected):
        '''
        Trains the ESN given an input, for all the duration of the input, using linear regression.
        The objective of the ESN will be to match the expected result, simulated with the given inputs. It should then be able to evolve on its own.
        inputs and expected should be of the same size.
        '''
        print("---Beginning training---")
        X = np.zeros((len(inputs),self.N))
        for i in range(1,len(inputs)):
            X[i] = self.x["activity"] * self.connection_out    #So that the regression only sees the neurons connected to the output.
            self.update(inputs[i],addNoise = True)
        newWeights = np.dot(np.dot(expected.T,X), np.linalg.inv(np.dot(X.T,X) + epsilon*np.eye(self.N)))    #The linear regression
        self.W_out = newWeights
        print("---Training done---")
        self.istrained = True
        self.y = self.W_out @ self.x["activity"]   #Output state of the reservoir. After this, it will be computed from the state of the reservoir in the update function.

    def generateNoise(self):
        return self.noise * np.random.uniform(-1,1,(self.number_input)) #A random vector beetween -noise and noise

    def simulation(self, nb_iter, inputs = [], expected = [],len_warmup = 0 ,len_training = 0, delay = 0, reset = False):
        '''
        Simulates the behaviour of the ESN given :
        - input : a starting sequence, wich will be followed.
        - nb_iter: number of iteration the ESN will run alone (ie simulate)
        - len_warmup: number of iterations of the warmup sequence.
        - len_training: number of iteration of the training sequence.
        - reset: wether the coeffs of the ESN are reset or not. This will not undo training, and you must use reset_reservoir manually if you want to.

        Input must at least be of length len_warmup + len_training.
        '''
        self.len_warmup = len_warmup
        self.len_training = len_training
        assert len_warmup + len_training <= len(inputs), "Insufficient input size"
        if reset :
            self.reset_reservoir()  #initial reset for multiple calls
        if len_warmup > 0 :
            self.warmup(inputs[:len_warmup])
        if len_training > 0 :
            self.train(inputs[len_warmup:len_warmup+len_training],expected[:len_training])
        print("---Begining simulation without input---")
        predictions = []
        for _ in range(nb_iter):
            self.update(self.y)
            predictions.append(self.y)
        print("---Simulation done---")
        return predictions

    def begin_record(self):
        self.isRecording = True
        self.historic = []
        self.record_state()

    def end_record(self,name, bin_len = 0.1, isDisplayed = False):
        figure = plt.figure(figsize = (5,7))
    #    figure, axes = plt.subplots(nrows = 2,ncols = 1,sharex = True, frameon=False)
        title = figure.suptitle("Warmup: Step n°0")
        gs = gridspec.GridSpec(2, 1, height_ratios=[2,1])
        axes = [plt.subplot(gs[0]), plt.subplot(gs[1])]
        bins = np.arange(0, 1 + bin_len, bin_len)
        bin_position = np.array([(self.x["position"][:,0] >= bins[i]) * (self.x["position"][:,0] < bins[i+1]) for i in range(len(bins)-1)])

        axes[0].set_title("Neurons position and activity")

        #Draws the vertical liines.
        for x_value in bins[1:]:
            axes[0].plot([x_value,x_value],[0,0.5],'--',c = 'b')

        #Histogram setup
        value = [np.mean(self.historic[0]*(self.x["position"][:,0] >= bins[i]) * (self.x["position"][:,0] < bins[i+1])) for i in range(len(bins)-1)]
        bar = axes[1].bar(bins[:-1] + bin_len / 2 ,value,width = bin_len)
        axes[1].set_title("Global value according to x position")

        #We add 4 dummy points for display (see https://stackoverflow.com/questions/20515554/colorize-voronoi-diagram)
        vor = Voronoi(np.concatenate((self.x["position"],np.array([[999,999],[-999,999],[999,-999],[-999,-999]]))))
        voronoi_plot_2d(vor,axes[0],show_points=False, show_vertices=False, s=1)

        self.historic = np.array(self.historic)
        nb_states,nb_neurons = self.historic.shape
        colors_array = np.zeros((nb_states,nb_neurons,4))

        #Creates mean array:
        len_mean = 20
        mean_array = np.zeros((nb_states+len_mean,nb_neurons))
        for j in range(len_mean):
            mean_array += np.concatenate((np.zeros((j,nb_neurons)),self.historic,np.zeros((len_mean-j,nb_neurons))))
        mean_array *= 1/len_mean

        print("---Computing colors---")
        for i in range(self.N):
            max = np.max(np.abs(self.historic[:,i]))
            #norm = mpl.colors.Normalize(vmin =  -1 , vmax = 1)  #Each neuron is normalized according to its
            norm = mpl.colors.Normalize(vmin =  -max , vmax = max)  #Each neuron is normalized according to its maximum value,centered on 0.

            mapper = cm.ScalarMappable(norm = norm, cmap = cm.coolwarm)  #The Voronoi colormap
            #colors_array[:,i] = mapper.to_rgba(self.historic[:,i])
            colors_array[:,i] = mapper.to_rgba(mean_array[:-len_mean,i])

        print("---Done---")
        #list_fills = []
        polygons = []
        facecolors = []
        for neuron_index in range(self.N):
            region = vor.regions[vor.point_region[neuron_index]]
            polygon = [vor.vertices[i] for i in region]
            polygons.append(polygon)
            facecolors.append((0,0,0,1))

            #list_fills.append(axes[0].fill(*zip(*polygon), color=mapper.to_rgba(self.historic[0][neuron_index])))


        axes[0].set_ylim(0,self.ymax)
        axes[0].set_xlim(0,1)

        axes[0].set_aspect(1)
        polycollection = mpl.collections.PolyCollection(polygons)
        #colors_array = mapper.to_rgba(np.copy(self.historic))   #Maps the color of each past activity to display.
        #colors_array = mapper.to_rgba(self.historic * (1+ 2*self.x["position"][:,0]))   #Maps the color of each past activity to display while amplifying the behaviour for neurons furthers in the reservoir.
        polycollection.set_facecolors(colors_array[0])
        polycollection.set_edgecolors("white")
        axes[0].add_collection(polycollection)
        figure.tight_layout(pad=3.0)


        def update_frame(i):

            #Update of the neurons display
            #scat.set_array(self.historic[i])
            title.set_text("{}: Step n°{}".format("Warmup" if i < len_warmup else ("Training" if i < len_warmup + len_training else "Prediction"),i))

            #Update of the histogram
            value = [np.mean(self.historic[i]* bin_position[j]) for j in range(len(bins)-1)]
            #We take the mean inside the bin interval
            for rect,h in zip(bar,value):
                rect.set_height(h)

            polycollection.set_facecolors(colors_array[i])
            '''
            count = 0
            for fill in list_fills:
                newcolor = colors_array[i][count]
                #print(newcolor)
                .set_fc(newcolor)
                count += 1'''
            #print(fill[0].get_facecolor())
            #return bar, list_fills

        anim = animation.FuncAnimation(figure, update_frame,frames = np.arange(1,len(self.historic)),interval = 10)
        if name != "":
            print("---Saving the animation---")
            anim.save(name+".mp4", fps=30)
            print("---Saving done---")
        if isDisplayed:
            plt.show()

        plt.close()
        self.isRecording = False

    def record_state(self):
        '''
        Stores an array of the current activity state.
        '''
        self.historic.append(np.copy(self.x["activity"]))

    def disp_connectivity(self):
        '''
        Displays the connections inside the reservoir, majoritarly to see what happens during spatialization.
        The plot is interactive.
        '''

        connection_in = (self.W_in != 0)
        if len(self.connection_out.shape) == 1:
            connection_out = self.connection_out[np.newaxis].T
        else:
            connection_out = self.connection_out

        intern_connections = (self.W != 0)
        figure, axes = plt.subplots(nrows=2, ncols=1, figsize=(20,20))

        print("Number of connection to the reservoir : ",np.sum(connection_in))
        print("Number of connection inside the reservoir : ",np.sum(intern_connections))
        print("Number of connection to the output : ",np.sum(connection_out))

        figure.suptitle("{} neurons, external sparsity = {} ".format(self.N, self.external_sparsity))

        print("---Placing the neurons, this migth take a while---")
        #For the initial display, we show the connection to input and output -> the following lines compute them
        connection_input = []
        connection_output = []
        connection_both = []
        unrelated = []
        for i in range(self.N):
            connected_output = connection_out[i,:].any()
            connected_input = connection_in[i,:].any()
            if connected_input and connected_output:
                connection_both.append(i)
            elif connected_input:
                connection_input.append(i)
            elif connected_output:
                connection_output.append(i)
            else:
                unrelated.append(i)

        #Initialisation of the plots
        unrelatedNeurons = axes[0].scatter(self.x["position"][unrelated][:,0],self.x["position"][unrelated][:,1],c = 'b')
        previousNeurons =  axes[0].scatter(self.x["position"][connection_input][:,0],self.x["position"][connection_input][:,1],c = 'r')
        selectedNeuron =  axes[0].scatter(self.x["position"][connection_both][:,0],self.x["position"][connection_both][:,1],c = 'g')
        nextNeurons = axes[0].scatter(self.x["position"][connection_output][:,0],self.x["position"][connection_output][:,1],c = 'y')
        axes[0].legend((previousNeurons,nextNeurons,selectedNeuron),("Connected to the input","Connected to the output","Connected to both"),fontsize=6)

        axes[0].set_aspect(1)

        #We draw the arrows
        arrows = []
        for i in range(self.N):
            for j in range(self.N):
                if self.W[i,j] != 0:
                    arrow = axes[0].plot([self.x["position"][i,0],self.x["position"][j,0]], [self.x["position"][i,1], self.x["position"][j,1]],c = 'b',lw = 0.1)
                    arrows.append(arrow)

        arrowDisplayed = [True]
        print("---Done---")

        def onClick(event):
            '''
            When the mouse is clicked, change the focus on the nearest neuron, and display its past activity in the lower plot.
            '''
            index = self.get_nearest_index(event.xdata,event.ydata) #Gets the index of the clicked neuron
            print("Clicked on neuron {}, with position {}".format(index,self.x["position"][index]))

            #To better visualize the connections of the selected neuron
            previous = []
            next = []
            unrelated = []
            for j in range(self.N):
                #We check the relation with the others neurons
                if j != index:
                    if self.W[j,index] != 0:
                        next.append(j)
                    elif self.W[index,j] != 0:
                        previous.append(j)
                    else:
                        unrelated.append(j)

            unrelatedNeurons.set_offsets(self.x["position"][unrelated])
            previousNeurons.set_offsets(self.x["position"][previous])
            nextNeurons.set_offsets(self.x["position"][next])
            selectedNeuron.set_offsets(self.x["position"][index])
            axes[0].legend((selectedNeuron,previousNeurons,nextNeurons),("Selected Neuron","Previous Neurons","Next Neurons"),fontsize=6)

            axes[1].clear()
            axes[1].set_title("Past activity of neuron {}".format(index))
            axes[1].plot([self.len_warmup,self.len_warmup],[-1,1],'--')
            axes[1].plot([self.len_training+self.len_warmup,self.len_training+self.len_warmup],[-1,1],'--')
            axes[1].fill_between([0,self.len_warmup],[-1,-1],[1,1], color = 'green', alpha = 0.25, label = "Warmup phase" )
            axes[1].fill_between([self.len_warmup,self.len_warmup + self.len_training],[-1,-1],[1,1], color = 'Blue', alpha = 0.25, label = "Training phase" )
            axes[1].fill_between([self.len_warmup + self.len_training,self.n_iter + 1],[-1,-1],[1,1], color = 'Red', alpha = 0.25, label = "Simulation phase" )
            axes[1].set_ylim(-1,1)
            axes[1].legend()
            if self.historic != []:
                axes[1].plot([state[index] for state in self.historic])
            figure.canvas.draw()                                       #Updates visually

        def onPress(event):
            '''
            Displays the connection arrows when the key space is pressed, and remove them when it is pressed again
            When escape key is pressed, reset the display to see the neurons connected to the input/output.
            '''
            if event.key == " ":
                if arrowDisplayed[0]:
                    for arrow in arrows:
                        arrow[0].set_visible(False)
                else:
                    for arrow in arrows:
                        arrow[0].set_visible(True)
                arrowDisplayed[0] = not(arrowDisplayed[0])
                figure.canvas.draw()

            elif event.key == "escape": #To loose focus on the neuron => set the plot back to its original state
                unrelatedNeurons.set_offsets(self.x["position"][unrelated])
                previousNeurons.set_offsets(self.x["position"][connection_input])
                nextNeurons.set_offsets(self.x["position"][connection_output])
                selectedNeuron.set_offsets(self.x["position"][connection_both])
                axes[0].legend((previousNeurons,nextNeurons,selectedNeuron),("Connected to the input","Connected to the output","Connected to both"),fontsize=6)
                figure.canvas.draw()

        figure.canvas.mpl_connect('button_press_event',onClick)
        figure.canvas.mpl_connect('key_press_event',onPress)
        print("---Displaying---")
        plt.show()
        print("---Done---")
        plt.close()

    def copy(self):
        '''
        Returns an independent copy of the current ESN. Used to compare different ESN with same initialization.
        '''
        print("---Beginning copying---")
        buffer = Spatial_ESN(number_neurons = self.N, external_sparsity = self.external_sparsity,intern_sparsity = self.intern_sparsity, \
            number_input = self.number_input,number_output = self.number_output,\
            spectral_radius = self.spectral_radius,leak_rate = self.leak_rate,noise = self.noise,isCopy = True)
        buffer.N = self.N
        buffer.W = np.copy(self.W)
        buffer.W_in = np.copy(self.W_in)
        buffer.W_out = np.copy(self.W_out)
        buffer.connection_out = np.copy(self.connection_out)
        buffer.W_back = np.copy(self.W_back)
        buffer.x = np.copy(self.x)
        buffer.y = np.copy(self.y)
        buffer.n_iter = self.n_iter
        print("---Copying done---")
        return buffer

    def get_nearest_index(self,x,y):
        '''
        Given a position in the plane, returns the index of the nearest neuron
        :parameters: x,y : two floats.
        Output: returns a tuple
        '''

        distances = distance.cdist(self.x["position"],[[x,y]])
        ind = np.unravel_index(np.argmin(distances, axis=None), distances.shape) #Gets the index of the minimum of the distances array
        return (ind[0])

#----------------------------------------------------------------------------------------------------------------------
#Treatment functions. Used for display and to obtain results
def compute_error(result,expected):
    "Computes a least squared error between two arrays."
    gap = 0
    for i in range(len(result)):
        gap += np.linalg.norm(result[i]-expected[i])
    return gap

def plot_distance(result,expected,beginning_len,title = "Comparison of efficiency"):
    duration = len(result)
    fig,axes = plt.subplots(nrows = 2, ncols = 1, sharex = True)
    x = [i for i in range(beginning_len,beginning_len + duration)]
    y = np.abs(np.array(result) - np.array(expected)[beginning_len:beginning_len +duration,])
    axes[0].plot(x, y)
    axes[1].plot(x, y)
    axes[1].set_title("Zoomed in version")
    axes[0].set_title(title)
    axes[1].set_ylim([0,1])
    plt.xlabel("Epochs")
    fig.text(0.06, 0.5, 'Distance between expected and real signal', ha='center', va='center', rotation='vertical')

    plt.show()

def compare_prediction(esn,input,label_input ,len_warmup,len_training, delays = [0],nb_iter = -1, display_anim = True,display_connectivity = True,bin_size = 0.1, savename = ""):
    '''
    Trains the network, and display both the expected result and the network output. Can also save/display the plot of the inner working.
    :parameters:
        - esn : an instance of Spatial_ESN
        - input : the input series
        - label_input : the name for the plot
        - len_warmup: For how long the ESN is warmupped
        - len_training : the length of the training
        - nb_iter : for how long the simulation is done after training. Computed by default to fit the length of input
        - displayAnim : Wether the internal state is plotted
        - savename: optionnal, where the .mp4 is generated. If not filled, it won't be generated.
    '''

    display = display_anim or (savename != "")
    if display or display_connectivity: #We need to record the states for both display methods.
        esn.begin_record()
    if nb_iter ==-1:
        nb_iter = len(input) - len_warmup - len_training
    print("Nb_iter: ",nb_iter)

    simus = []      #To handle several copies of a simulation. Used to compare the efficiency of delay.
    for i in range(len(delays)-1):
        expected = input[len_warmup + delays[i]:len_warmup + delays[i] + len_training] #The awaited results during the training. delays allow to offset the expected result, due to delay to cross the reservoir.
        copy = esn.copy()
        simus.append(copy.simulation(nb_iter = nb_iter, inputs = input, expected = expected, len_warmup = len_warmup, len_training = len_training, reset = False ))


    expected = input[len_warmup - delays[-1]:len_warmup - delays[-1] + len_training] #The awaited results during the training.
    simus.append(esn.simulation(nb_iter = nb_iter, inputs = input, expected = expected, len_warmup = len_warmup, len_training = len_training, reset = False))
    if display:
        esn.end_record(savename, bin_len = bin_size, isDisplayed = display_anim)
    if display_connectivity:
        esn.disp_connectivity()

    #Multiple sublots handling. More complicated than necessary, but should be able to adapt to any number of delay input (still must be visible)
    nb_cols = 2 if len(delays) >2 else 1
    nb_lines = ceil(len(delays)/2) if len(delays) > 2 else len(delays)

    fig,axes = plt.subplots(nrows = nb_lines, ncols = nb_cols, sharex = True, sharey = False)
    if nb_lines == 1:
        axes = [[axes]]
    elif nb_cols == 1:
        axes = list(map(lambda x : [x],axes))

    min_error = np.inf
    optimal_delay = -1
    i,j = 0,0
    while nb_cols*(i) + j+1 <= len(delays):
        x = range(len_warmup+len_training,nb_iter+len_warmup+len_training)
        expected = input[len_warmup + len_training - delays[nb_cols*i + j] : nb_iter + len_warmup + len_training - delays[nb_cols*i + j]]
        axes[i][j].plot(x, expected ,'--',label = label_input)
        axes[i][j].plot(x, simus[nb_cols*i + j],'-', label = "ESN response")
        axes[i][j].set_title("Delay: {} steps".format(delays[nb_cols*i + j]))

        error = compute_error(simus[nb_cols*i + j],expected)
        if error < min_error:
            min_error = error
            optimal_delay = delays[nb_cols*i + j]
        print("Training delay: {} ---- Error : {}".format(delays[nb_cols*i + j],error))
        if j == nb_cols - 1:
            j=0
            i+=1
        else:
            j+=1
        #axes[i][j].legend()
    fig.suptitle("ESN with {} neurons\n external sparsity: {}\n internal sparsity {}".format(esn.N,esn.external_sparsity,esn.intern_sparsity))
    #fig.tight_layout(pad=3.0)
    if len(delays) <=4:
        plt.legend()
    print("The optimal delay for those parameters is {},with an error of {}".format(optimal_delay,min_error))
    plt.show()
    plt.close()
    plot_distance(expected = input, result = simus[0],beginning_len = len_warmup + len_training)

def generate_basic_ESN(number_neurons, sparsity, number_input, number_output, spectral_radius, leak_rate, noise):
    '''
    Creates a basic ESN, but using the spatial ESN. The idea is to be able to compare the results.
    '''
    buffer = Spatial_ESN(number_neurons = number_neurons, external_sparsity = 1,intern_sparsity = sparsity, number_input = number_input, \
                    number_output = number_output, spectral_radius = spectral_radius, leak_rate = leak_rate, noise = noise)

    #We must regenerate the W matrix, since it is generated with space contraints otherwise.
    buffer.N = number_neurons
    buffer.W = np.random.uniform(-1,1,(number_neurons,number_neurons))
    intern_connections = (np.random.uniform(0,1,buffer.W.shape) < sparsity)
    buffer.W *= intern_connections

    current_radius = np.max(np.abs(np.linalg.eigvals(buffer.W)))
    if current_radius == 0.0:
        raise Exception("Null Spectral radius for generated matrix")
    else:
        buffer.W *= spectral_radius/current_radius            #We normalize the weight matrix to get the desired spectral radius.
    buffer.W_in = 0.5 * np.random.uniform(-1,1,(number_neurons, 1 + number_input))    #We initialise between -1 and 1 uniformly, maybe to change
    buffer.W_out = 0.5 * np.random.uniform(-1,1,(number_output, number_neurons))
    buffer.connection_out = np.ones(buffer.W_out.shape)
    buffer.x = np.zeros((number_neurons),dtype = [("activity",float),("position",float,(2,)),("mean",float)])
    buffer.x["activity"] = np.random.uniform(-1,1,(number_neurons,))   #Internal state of the reservoir. Initialisation might change

    buffer.x["mean"] = np.copy(buffer.x["activity"])
    return buffer

def disp_sorted_matrix(esn):
    '''
    Takes an esn and displays its W matrix sorted by ascending x.
    '''
    W = np.copy(esn.W)
    posx = esn.x["position"][:,0]
    matrix = np.zeros((esn.N),dtype = [("x",float),("connection",float,(esn.N,))])
    print(matrix[:]["x"].shape,posx.shape)
    for neuron in range (esn.N):
        matrix[neuron]["x"] = posx[neuron]
        matrix[neuron]["connection"] = W[neuron]    #Connection will describe the previous neurons, connected to this one

    matrix.sort(axis = 0,order = "x")
    for neuron in range(esn.N):
        W[neuron] = np.copy(matrix[neuron]["connection"])

    for neuron1 in range(esn.N):
        for neuron2 in range(neuron1+1,esn.N):
            if matrix[neuron1]["x"]>matrix[neuron2]["x"]:
                print("Backward connexion",neuron1,";",neuron2,";",posx[neuron1],";", posx[neuron2])
    is_connected = (W != 0)
    deltax = np.tile(matrix["x"],(esn.N,1))
    deltax = (deltax.T - deltax)
    print("Test display",np.sum((deltax.T * is_connected) <0))
    ind = np.unravel_index(np.argmin(deltax*is_connected, axis=None), deltax.shape) #Gets the index of the minimum of the distances array
    if (deltax*is_connected)[ind] <0:
        print("Negative distance connections, index {}, deltax = {}".format(ind,deltax[ind]))
    fig = plt.figure()
    ax = plt.subplot(1,1,1, aspect=1, frameon=False)
    image = ax.imshow(W,cmap = cm.coolwarm ,vmin = np.min(W), vmax = np.max(W))
    fig.suptitle("Matrix of size {}x{}\n{} effective connections\nLines of W are sorted according to ascending x".format(esn.N,esn.N,np.sum(is_connected)))
    plt.show()
#----------------------------------------------------------------------------------------------------------------------
#File and json handling

def get_git_revision_hash():
    """ Get current git hash """
    answer = subprocess.check_output(['git', 'rev-parse', 'HEAD'])
    return answer.decode("utf8").strip("\n")

def get_git_revision_branch():
    """ Get current git branch """
    answer = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    return answer.decode("utf8").strip("\n")

def default():
    """ Get default parameters """
    _data["timestamp"] = time.ctime()
    _data["git_branch"] = get_git_revision_branch()
    _data["git_hash"] = get_git_revision_hash()
    return _data

def save(filename, data=None):
    """ Save parameters into a json file """
    if data is None:
       data = { name : eval(name) for name in _data.keys()
                if name not in ["timestamp", "git_branch", "git_hash"] }
    data["timestamp"] = time.ctime()
    data["git_branch"] = get_git_revision_branch()
    data["git_hash"] = get_git_revision_hash()
    with open(filename, "w") as outfile:
        json.dump(data, outfile,indent = 1)

def load(filename):
    """ Load parameters from a json file """
    with open(filename) as infile:
        data = json.load(infile)
    return data

def dump(data):
    for key, value in data.items():
        print(f"{key:15s} : {value}")

#----------------------------------------------------------------------------------------------------------------------

if __name__  == "__main__":
    #Save of parameters. Rename file afterward.
    save("temp.txt", _data)
    data = load("temp.txt")
    dump(data)
    locals().update(data)
    save("temp.txt")

    if savename != "":
        save(savename+".txt")
    #Beginning of execution
    np.random.seed(seed)

    #Training and samplig dataset import.
    if label_input == "Mackey Glass":
        input = np.load("mackey-glass.npy")[np.newaxis].T
    elif label_input == "Sinus":
        t = np.arange(start = 0,stop = 1000,step = 1/10)
        input = np.sin(t) + 0.1 * np.cos(10*t)
    elif label_input == "Constant":
        input = 10 * np.ones((1000000))
    #Creating the ESN
    spatial_esn = Spatial_ESN(number_neurons = number_neurons, external_sparsity = external_sparsity,\
                      intern_sparsity = intern_sparsity, number_input = 1, number_output = 1,\
                      spectral_radius = spectral_radius, leak_rate = leak_rate, noise = noise)
    regular_esn = generate_basic_ESN(number_neurons = number_neurons,\
                      sparsity = intern_sparsity, number_input = 1, number_output = 1,\
                      spectral_radius = spectral_radius, leak_rate = leak_rate, noise = noise)

    spatial_esn.W_back *= 0
    spatial_esn.x["activity"]*=0
    #test.W_in = (test.W_in != 0)
    #test.W = (test.W != 0)
    print("Effective spectral radius :",max(abs(np.linalg.eig(spatial_esn.W)[0]))) #Check wether the spectral radius is respected.
    disp_sorted_matrix(spatial_esn)

    compare_prediction(spatial_esn,input = input,len_warmup = len_warmup, len_training = len_training, delays = delays, nb_iter = simulation_len,display_anim = display_animation,\
        display_connectivity = display_connectivity ,bin_size = bin_size,savename = savename,label_input = label_input + " series")
    '''
    compare_prediction(regular_esn,input = input,len_warmup = len_warmup, len_training = len_training, delays = delays, nb_iter = simulation_len,display_anim = False,\
    display_connectivity = False ,bin_size = bin_size,savename = "",label_input = label_input + " series")
    '''
    connection_in_spatial = (spatial_esn.W != 0)
    connection_in_basic = (regular_esn.W != 0)
    print("Nb of connections in the spatial ESN: {} \nNb of connections in the regular ESN: {}".format(np.sum(connection_in_spatial),np.sum(connection_in_basic)))
